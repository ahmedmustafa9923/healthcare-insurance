"""member-records-mcp: the ONLY path for agents to change member and lead data.

Every change follows propose -> review -> apply, stored in the change-requests table:
  propose_change  creates a pending request (with a before-snapshot), never touches data
  review_change   approves or rejects; HIGH-risk changes need human_confirmed=true
  apply_change    executes ONLY approved requests, records the after-snapshot (audit trail)
"""
import hashlib
import os
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

REGION = os.environ.get("AWS_REGION", "us-east-1")
REQUESTS_TABLE = os.environ.get("CHANGE_REQUESTS_TABLE", "healthcare-change-requests")
dynamodb = boto3.resource("dynamodb", region_name=REGION)
requests_table = dynamodb.Table(REQUESTS_TABLE)

Provision = Literal[
    "blue-cross-personal", "blue-cross-business",
    "hartford-personal", "hartford-business",
    "all-state-personal", "all-state-business",
]
Action = Literal[
    "create_member", "update_member", "soft_delete_member", "hard_delete_member",
    "create_lead", "update_lead_status",
]
HIGH_RISK = {"hard_delete_member"}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+1\d{10}$")
UPDATABLE_MEMBER_FIELDS = {"first_name", "last_name", "email", "phone",
                           "consent_email", "consent_sms", "monthly_premium"}
LEAD_STATUSES = {"new", "contacted", "converted", "closed"}

mcp = FastMCP(
    name="member-records",
    instructions=(
        "Changes to member and lead records. Flow: propose_change -> review_change -> "
        "apply_change. apply_change only runs approved requests. hard_delete_member is "
        "high risk and needs human_confirmed=true at review."
    ),
)


# ---------- helpers ----------

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def plain(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [plain(x) for x in v]
    return v


def mask(item):
    if not item:
        return item
    out = dict(item)
    if "email" in out:
        user, _, domain = str(out["email"]).partition("@")
        out["email"] = f"{user[:1]}***@{domain}"
    if "phone" in out:
        out["phone"] = f"***-***-{str(out['phone'])[-4:]}"
    return plain(out)


def short_hash(*parts):
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12].upper()


def member_prefix(provision):
    carrier, lob = provision.rsplit("-", 1)
    return f"{carrier[:2].upper()}{lob[0].upper()}"


def table_for(provision, action):
    kind = "leads" if action in ("create_lead", "update_lead_status") else "members"
    pk = "lead_id" if kind == "leads" else "member_id"
    return dynamodb.Table(f"{provision}-{kind}"), pk


def check_contact(fields):
    errors = []
    if "email" in fields and not EMAIL_RE.match(str(fields["email"])):
        errors.append("email is not valid")
    if "phone" in fields and not PHONE_RE.match(str(fields["phone"])):
        errors.append("phone must look like +15555550123")
    for f in ("consent_email", "consent_sms"):
        if f in fields and not isinstance(fields[f], bool):
            errors.append(f"{f} must be true or false")
    return errors


def validate(provision, action, target_id, changes):
    """Return (target_id, clean_changes) or raise ToolError listing every problem."""
    errors, clean = [], dict(changes or {})

    if action == "create_member":
        for f in ("first_name", "last_name", "email", "phone", "enrolled_date"):
            if not clean.get(f):
                errors.append(f"{f} is required")
        clean.setdefault("consent_email", False)
        clean.setdefault("consent_sms", False)
        try:
            clean["enrolled_date"] = date.fromisoformat(str(clean.get("enrolled_date"))).isoformat()
        except ValueError:
            errors.append("enrolled_date must be YYYY-MM-DD")
        errors += check_contact(clean)
        if not errors:
            clean["email"] = clean["email"].lower()
            target_id = f"{member_prefix(provision)}-F{short_hash(provision, clean['email'])}"

    elif action == "create_lead":
        for f in ("first_name", "last_name", "email", "phone"):
            if not clean.get(f):
                errors.append(f"{f} is required")
        clean.setdefault("consent_email", False)
        clean.setdefault("consent_sms", False)
        errors += check_contact(clean)
        if not errors:
            clean["email"] = clean["email"].lower()
            target_id = f"LD-{short_hash(provision, clean['email'])}"

    elif action == "update_member":
        bad = set(clean) - UPDATABLE_MEMBER_FIELDS
        if bad:
            errors.append(f"fields not allowed: {sorted(bad)}; allowed: {sorted(UPDATABLE_MEMBER_FIELDS)}")
        if not clean:
            errors.append("changes must include at least one field")
        errors += check_contact(clean)
        if "monthly_premium" in clean:
            try:
                clean["monthly_premium"] = Decimal(str(clean["monthly_premium"]))
                if clean["monthly_premium"] <= 0:
                    errors.append("monthly_premium must be > 0")
            except Exception:
                errors.append("monthly_premium must be a number")

    elif action == "update_lead_status":
        if clean.get("lead_status") not in LEAD_STATUSES or set(clean) != {"lead_status"}:
            errors.append(f"changes must be exactly {{'lead_status': one of {sorted(LEAD_STATUSES)}}}")

    elif action in ("soft_delete_member", "hard_delete_member"):
        clean = {}

    if action not in ("create_member", "create_lead") and not target_id:
        errors.append("target_id is required for this action")
    if errors:
        raise ToolError("; ".join(errors))
    return target_id, clean


def load_request(request_id):
    item = requests_table.get_item(Key={"request_id": request_id}).get("Item")
    if not item:
        raise ToolError(f"Change request {request_id} not found.")
    return item


def summary(item):
    out = {k: item.get(k) for k in (
        "request_id", "status", "risk", "provision", "action", "target_id", "changes",
        "reason", "requested_by", "reviewed_by", "review_note", "human_confirmed",
        "created_at", "reviewed_at", "applied_at", "before", "after")}
    return mask_snapshot(plain({k: v for k, v in out.items() if v is not None}))


def mask_snapshot(d):
    for k in ("before", "after", "changes"):
        if isinstance(d.get(k), dict):
            d[k] = mask(d[k])
    return d


# ---------- tools ----------

@mcp.tool(annotations={"title": "Propose change", "readOnlyHint": False, "destructiveHint": False})
def propose_change(
    provision: Provision,
    action: Action,
    requested_by: Annotated[str, Field(min_length=2, max_length=60, description="Agent or person asking, e.g. owner-agent")],
    reason: Annotated[str, Field(min_length=5, max_length=500, description="Why this change is needed")],
    target_id: Annotated[Optional[str], Field(description="member_id or lead_id; omit for create_* actions")] = None,
    changes: Annotated[Optional[dict[str, Any]], Field(description="Fields to set. create_member: first_name, last_name, email, phone, enrolled_date (YYYY-MM-DD), consent_email, consent_sms. update_member: any of first_name, last_name, email, phone, consent_email, consent_sms, monthly_premium. update_lead_status: {lead_status}.")] = None,
) -> dict:
    """Create a PENDING change request. Does not modify any member or lead data."""
    target_id, clean = validate(provision, action, target_id, changes)
    table, pk = table_for(provision, action)
    before = table.get_item(Key={pk: target_id}).get("Item")

    if action in ("create_member", "create_lead") and before:
        raise ToolError(f"{target_id} already exists in {provision}; use an update action instead.")
    if action not in ("create_member", "create_lead") and not before:
        raise ToolError(f"{target_id} not found in {provision}.")
    if action == "soft_delete_member" and before.get("status") == "deleted":
        raise ToolError(f"{target_id} is already soft-deleted.")

    item = {
        "request_id": f"CR-{uuid.uuid4().hex[:10].upper()}",
        "status": "pending",
        "risk": "high" if action in HIGH_RISK else "low",
        "provision": provision, "action": action, "target_id": target_id,
        "changes": clean, "reason": reason, "requested_by": requested_by,
        "created_at": now(),
    }
    if before:
        item["before"] = before
    requests_table.put_item(Item=item)
    return summary(item)


@mcp.tool(annotations={"title": "Review change", "readOnlyHint": False, "destructiveHint": False})
def review_change(
    request_id: Annotated[str, Field(pattern=r"^CR-[0-9A-F]{10}$")],
    decision: Literal["approve", "reject"],
    reviewer: Annotated[str, Field(min_length=2, max_length=60)],
    note: Annotated[str, Field(max_length=500)] = "",
    human_confirmed: Annotated[bool, Field(description="True only after a human explicitly approved this exact request")] = False,
) -> dict:
    """Approve or reject a PENDING change request. High-risk requests need human_confirmed=true to approve."""
    item = load_request(request_id)
    if item["status"] != "pending":
        raise ToolError(f"{request_id} is {item['status']}, only pending requests can be reviewed.")
    if decision == "approve" and item["risk"] == "high" and not human_confirmed:
        raise ToolError(f"{request_id} is high risk ({item['action']}); a human must confirm before approval.")

    status = "approved" if decision == "approve" else "rejected"
    requests_table.update_item(
        Key={"request_id": request_id},
        UpdateExpression="SET #s = :s, reviewed_by = :r, review_note = :n, human_confirmed = :h, reviewed_at = :t",
        ConditionExpression="#s = :pending",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":r": reviewer, ":n": note, ":h": human_confirmed,
                                   ":t": now(), ":pending": "pending"},
    )
    return summary(load_request(request_id))


@mcp.tool(annotations={"title": "Apply change", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True})
def apply_change(request_id: Annotated[str, Field(pattern=r"^CR-[0-9A-F]{10}$")]) -> dict:
    """Execute an APPROVED change request against the member/lead tables. Refuses anything not approved."""
    item = load_request(request_id)
    if item["status"] == "applied":
        return summary(item)
    if item["status"] != "approved":
        raise ToolError(f"{request_id} is {item['status']}; only approved requests can be applied.")

    provision, action, target, changes = item["provision"], item["action"], item["target_id"], item["changes"]
    table, pk = table_for(provision, action)
    carrier, lob = provision.rsplit("-", 1)

    if action == "create_member":
        table.put_item(Item={**changes, pk: target, "status": "active", "onboarding_stage": "day0",
                             "carrier": carrier, "line_of_business": lob, "source": "agent"},
                       ConditionExpression=f"attribute_not_exists({pk})")
    elif action == "create_lead":
        table.put_item(Item={**changes, pk: target, "lead_status": "new",
                             "received_date": date.today().isoformat(),
                             "carrier": carrier, "line_of_business": lob, "source": "agent"},
                       ConditionExpression=f"attribute_not_exists({pk})")
    elif action in ("update_member", "update_lead_status"):
        names = {f"#f{i}": k for i, k in enumerate(changes)}
        values = {f":v{i}": v for i, v in enumerate(changes.values())}
        table.update_item(Key={pk: target},
                          UpdateExpression="SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(changes))),
                          ConditionExpression=f"attribute_exists({pk})",
                          ExpressionAttributeNames=names, ExpressionAttributeValues=values)
    elif action == "soft_delete_member":
        table.update_item(Key={pk: target},
                          UpdateExpression="SET #s = :d, deleted_at = :t REMOVE onboarding_stage",
                          ConditionExpression=f"attribute_exists({pk})",
                          ExpressionAttributeNames={"#s": "status"},
                          ExpressionAttributeValues={":d": "deleted", ":t": now()})
    elif action == "hard_delete_member":
        table.delete_item(Key={pk: target}, ConditionExpression=f"attribute_exists({pk})")

    after = table.get_item(Key={pk: target}).get("Item")
    expr = "SET #s = :a, applied_at = :t" + (", #after = :after" if after else "")
    values = {":a": "applied", ":t": now(), ":approved": "approved"}
    names = {"#s": "status"}
    if after:
        values[":after"] = after
        names["#after"] = "after"
    requests_table.update_item(Key={"request_id": request_id}, UpdateExpression=expr,
                               ConditionExpression="#s = :approved",
                               ExpressionAttributeNames=names, ExpressionAttributeValues=values)
    return summary(load_request(request_id))


@mcp.tool(annotations={"title": "Get change request", "readOnlyHint": True, "destructiveHint": False})
def get_change_request(request_id: Annotated[str, Field(pattern=r"^CR-[0-9A-F]{10}$")]) -> dict:
    """Fetch one change request with its status, decision and before/after snapshots (masked)."""
    return summary(load_request(request_id))


@mcp.tool(annotations={"title": "List change requests", "readOnlyHint": True, "destructiveHint": False})
def list_change_requests(status: Literal["pending", "approved", "rejected", "applied"] = "pending",
                         limit: Annotated[int, Field(ge=1, le=50)] = 10) -> list[dict]:
    """List change requests by status, newest first."""
    page = requests_table.query(IndexName="status-index", KeyConditionExpression=Key("status").eq(status),
                                ScanIndexForward=False, Limit=limit)
    return [summary(i) for i in page["Items"]]


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


