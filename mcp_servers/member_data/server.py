"""member-data-mcp: READ-ONLY MCP tools over the carrier DynamoDB tables.

Agents use these tools to answer questions about members, leads and revenue.
Contact details are always masked; nothing here can write or delete data.
"""
import os
from decimal import Decimal
from typing import Annotated, Literal

import boto3
from boto3.dynamodb.conditions import Key
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

REGION = os.environ.get("AWS_REGION", "us-east-1")
dynamodb = boto3.resource("dynamodb", region_name=REGION)

Provision = Literal[
    "blue-cross-personal", "blue-cross-business",
    "hartford-personal", "hartford-business",
    "all-state-personal", "all-state-business",
]
Limit = Annotated[int, Field(ge=1, le=50, description="Max results (1-50).")]

mcp = FastMCP(
    name="member-data",
    instructions=(
        "Read-only access to synthetic insurance member data for 6 provisions "
        "(carrier + line of business). Contact details are masked. Counts use indexes, "
        "so count_* tools are cheap; list_* tools return at most 50 records."
    ),
)


# ---------- helpers ----------

def plain(value):
    """DynamoDB returns Decimals; convert to JSON-friendly numbers."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def mask(item):
    """Never expose full contact details: g***@example.com, ***-***-0111, last initial."""
    out = dict(item)
    if "email" in out:
        user, _, domain = out["email"].partition("@")
        out["email"] = f"{user[:1]}***@{domain}"
    if "phone" in out:
        out["phone"] = f"***-***-{out['phone'][-4:]}"
    if "last_name" in out:
        out["last_name"] = out["last_name"][:1] + "."
    return plain(out)


def count_index(table, index, key_name, key_value):
    total, kwargs = 0, {"IndexName": index, "Select": "COUNT",
                        "KeyConditionExpression": Key(key_name).eq(key_value)}
    while True:
        page = table.query(**kwargs)
        total += page["Count"]
        if "LastEvaluatedKey" not in page:
            return total
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def list_index(table, index, key_name, key_value, limit, newest_first=True):
    page = table.query(IndexName=index, KeyConditionExpression=Key(key_name).eq(key_value),
                       ScanIndexForward=not newest_first, Limit=limit)
    return [mask(i) for i in page["Items"]]


# ---------- tools ----------

@mcp.tool(annotations={"title": "List provisions", "readOnlyHint": True, "destructiveHint": False})
def list_provisions() -> list[str]:
    """List the 6 carrier provisions (carrier-lineOfBusiness) that every other tool accepts."""
    return list(Provision.__args__)


@mcp.tool(annotations={"title": "Get member", "readOnlyHint": True, "destructiveHint": False})
def get_member(provision: Provision,
               member_id: Annotated[str, Field(pattern=r"^[A-Z]{3}-F?[0-9A-F]{7,12}$",
                                               description="e.g. BLP-0000123 or HAB-F1A2B3C4D5E6")]) -> dict:
    """Fetch one member by ID (masked contact details). Use list_* tools to discover IDs."""
    item = dynamodb.Table(f"{provision}-members").get_item(Key={"member_id": member_id}).get("Item")
    if not item:
        raise ToolError(f"Member {member_id} not found in {provision}. Check the provision or ID.")
    return mask(item)


@mcp.tool(annotations={"title": "Count onboarding members", "readOnlyHint": True, "destructiveHint": False})
def count_onboarding_members(provision: Provision,
                             stage: Literal["day0", "day7", "day30"]) -> dict:
    """Count new members currently at an onboarding stage (day0 = just enrolled)."""
    n = count_index(dynamodb.Table(f"{provision}-members"), "onboarding-index", "onboarding_stage", stage)
    return {"provision": provision, "stage": stage, "count": n}


@mcp.tool(annotations={"title": "List onboarding members", "readOnlyHint": True, "destructiveHint": False})
def list_onboarding_members(provision: Provision,
                            stage: Literal["day0", "day7", "day30"],
                            limit: Limit = 10) -> list[dict]:
    """List new members at an onboarding stage, most recently enrolled first (masked)."""
    return list_index(dynamodb.Table(f"{provision}-members"), "onboarding-index",
                      "onboarding_stage", stage, limit)


@mcp.tool(annotations={"title": "Count lapsed members", "readOnlyHint": True, "destructiveHint": False})
def count_lapsed_members(provision: Provision,
                         lapse_year: Annotated[int, Field(ge=2000, le=2100)]) -> dict:
    """Count inactive members whose policy lapsed in a given year (win-back candidates)."""
    n = count_index(dynamodb.Table(f"{provision}-members"), "lapsed-index", "lapse_year", str(lapse_year))
    return {"provision": provision, "lapse_year": lapse_year, "count": n}


@mcp.tool(annotations={"title": "List lapsed members", "readOnlyHint": True, "destructiveHint": False})
def list_lapsed_members(provision: Provision,
                        lapse_year: Annotated[int, Field(ge=2000, le=2100)],
                        limit: Limit = 10) -> list[dict]:
    """List inactive members who lapsed in a given year, most recent lapse first (masked)."""
    return list_index(dynamodb.Table(f"{provision}-members"), "lapsed-index",
                      "lapse_year", str(lapse_year), limit)


@mcp.tool(annotations={"title": "List leads", "readOnlyHint": True, "destructiveHint": False})
def list_leads(provision: Provision,
               status: Literal["new", "contacted", "converted"] = "new",
               limit: Limit = 10) -> list[dict]:
    """List prospective customers (leads) by status, newest first (masked)."""
    return list_index(dynamodb.Table(f"{provision}-leads"), "status-index",
                      "lead_status", status, limit)


@mcp.tool(annotations={"title": "Revenue summary", "readOnlyHint": True, "destructiveHint": False})
def revenue_summary(provision: Provision,
                    start_year: Annotated[int, Field(ge=2021, le=2100)] = 2021,
                    end_year: Annotated[int, Field(ge=2021, le=2100)] = 2026) -> dict:
    """Yearly premium revenue, claims paid, loss ratio and year-over-year growth for one provision."""
    if end_year < start_year:
        raise ToolError("end_year must be >= start_year")
    table = dynamodb.Table(f"{provision}-revenue")
    years, previous = [], None
    for year in range(start_year, end_year + 1):
        rows = table.query(KeyConditionExpression=Key("year").eq(str(year)))["Items"]
        if not rows:
            continue
        revenue = sum(r["premium_revenue"] for r in rows)
        claims = sum(r["claims_paid"] for r in rows)
        entry = {
            "year": year,
            "months": len(rows),
            "premium_revenue": round(float(revenue), 2),
            "claims_paid": round(float(claims), 2),
            "loss_ratio": round(float(claims / revenue), 3),
        }
        if previous and entry["months"] == previous["months"]:
            entry["yoy_growth"] = round(entry["premium_revenue"] / previous["premium_revenue"] - 1, 4)
        years.append(entry)
        previous = entry
    return {"provision": provision, "years": years,
            "note": "yoy_growth only when both years have the same number of months"}


# ---------- health check for Kubernetes probes ----------

@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

