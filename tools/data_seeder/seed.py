"""Synthetic data seeder: loads members + monthly revenue for ONE carrier/LOB.

Runs as a Kubernetes Indexed Job. JOB_COMPLETION_INDEX (0-5) picks the provision,
so 6 pods load the 6 provisions in parallel.

ALL DATA IS FAKE: emails use example.com and phones use 555-01xx, both reserved
and never deliverable, so no real person can ever be messaged.
"""
import os
import random
import time
from datetime import date, timedelta
from decimal import Decimal

import boto3

PROVISIONS = [
    ("blue-cross", "personal"), ("blue-cross", "business"),
    ("hartford", "personal"), ("hartford", "business"),
    ("all-state", "personal"), ("all-state", "business"),
]

FIRST = ["James", "Maria", "Robert", "Aisha", "Michael", "Priya", "David", "Sofia",
         "Daniel", "Fatima", "Joseph", "Mei", "Thomas", "Ana", "Kevin", "Grace",
         "Omar", "Elena", "Brian", "Nia"]
LAST = ["Smith", "Garcia", "Johnson", "Khan", "Williams", "Nguyen", "Brown", "Patel",
        "Jones", "Lopez", "Miller", "Chen", "Davis", "Ahmed", "Wilson", "Rossi",
        "Taylor", "Kim", "Moore", "Okafor"]

TODAY = date.today()


def money(x):
    return Decimal(str(round(x, 2)))


def make_member(i, carrier, lob, rng):
    first, last = rng.choice(FIRST), rng.choice(LAST)
    premium = rng.uniform(180, 950) if lob == "personal" else rng.uniform(900, 4800)
    item = {
        "member_id": f"{carrier[:2].upper()}{lob[0].upper()}-{i:07d}",
        "first_name": first,
        "last_name": last,
        "email": f"{first.lower()}.{last.lower()}.{i}@example.com",
        "phone": f"+1{rng.randint(201, 989)}55501{rng.randint(0, 99):02d}",
        "carrier": carrier,
        "line_of_business": lob,
        "monthly_premium": money(premium),
        "consent_email": rng.random() < 0.92,
        "consent_sms": rng.random() < 0.61,
    }

    roll = rng.random()
    if roll < 0.03:  # new member, still in onboarding
        days = rng.randint(0, 30)
        item["status"] = "active"
        item["enrolled_date"] = (TODAY - timedelta(days=days)).isoformat()
        item["onboarding_stage"] = "day0" if days < 7 else ("day7" if days < 30 else "day30")
    elif roll < 0.75:  # long-standing active member
        item["status"] = "active"
        item["enrolled_date"] = (TODAY - timedelta(days=rng.randint(31, 3650))).isoformat()
    else:  # inactive, candidate for win-back
        enrolled = TODAY - timedelta(days=rng.randint(3 * 365, 15 * 365))
        lapsed = enrolled + timedelta(days=rng.randint(365, (TODAY - enrolled).days - 30))
        item["status"] = "inactive"
        item["enrolled_date"] = enrolled.isoformat()
        item["lapsed_date"] = lapsed.isoformat()
        item["lapse_year"] = str(lapsed.year)
    return item


def revenue_rows(carrier, lob, members, rng):
    """Monthly premium revenue from Jan 2021 to the current month, with growth + seasonality."""
    avg = 565 if lob == "personal" else 2850
    base = members * 0.6 * avg
    growth = rng.uniform(0.04, 0.08)
    for year in range(2021, TODAY.year + 1):
        last_month = TODAY.month if year == TODAY.year else 12
        for month in range(1, last_month + 1):
            years_in = (year - 2021) + (month - 1) / 12
            seasonal = 1.06 if month == 1 else (0.97 if month in (7, 8) else 1.0)
            revenue = base * (1 + growth) ** years_in * seasonal * rng.uniform(0.97, 1.03)
            yield {
                "year": str(year),
                "month": f"{month:02d}",
                "carrier": carrier,
                "line_of_business": lob,
                "premium_revenue": money(revenue),
                "claims_paid": money(revenue * rng.uniform(0.72, 0.86)),
                "members_billed": int(members * 0.6 * (1 + growth) ** years_in),
            }


def main():
    index = int(os.environ["JOB_COMPLETION_INDEX"])
    total = int(os.environ.get("TOTAL_MEMBERS", "500000"))
    carrier, lob = PROVISIONS[index]
    per_provision = -(-total // len(PROVISIONS))  # round up
    rng = random.Random(index)  # deterministic: re-runs overwrite the same items

    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    members_table = dynamodb.Table(f"{carrier}-{lob}-members")
    revenue_table = dynamodb.Table(f"{carrier}-{lob}-revenue")

    print(f"[{carrier}-{lob}] seeding {per_provision:,} members", flush=True)
    start = time.time()
    with members_table.batch_writer(overwrite_by_pkeys=["member_id"]) as batch:
        for i in range(1, per_provision + 1):
            batch.put_item(Item=make_member(i, carrier, lob, rng))
            if i % 10000 == 0:
                print(f"[{carrier}-{lob}] {i:,} members ({i / (time.time() - start):,.0f}/s)", flush=True)

    rows = 0
    with revenue_table.batch_writer(overwrite_by_pkeys=["year", "month"]) as batch:
        for row in revenue_rows(carrier, lob, per_provision, rng):
            batch.put_item(Item=row)
            rows += 1

    print(f"[{carrier}-{lob}] done: {per_provision:,} members, {rows} revenue months "
          f"in {time.time() - start:,.0f}s", flush=True)


if __name__ == "__main__":
    main()

