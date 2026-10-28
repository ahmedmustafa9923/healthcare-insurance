"""Intake worker: turns CSV data feeds dropped in S3 into leads and members.

Flow per file (S3 -> SQS event -> this worker):
  incoming/<carrier>-<lob>/<name>.csv
    -> validate every row
    -> record_type=lead   -> <carrier>-<lob>-leads   (lead_status=new)
    -> record_type=member -> <carrier>-<lob>-members (status=active, onboarding_stage=day0)
    -> bad rows           -> rejected/<carrier>-<lob>/<name>-rejects.csv
    -> original file      -> processed/<carrier>-<lob>/<name>.csv
  Files with more than MAX_AUTO_ROWS rows go to pending-approval/ instead (a human
  or the Supervisor agent approves them later).

IDs are derived from provision + email, so re-sending the same feed never creates duplicates.
"""
import csv
import hashlib
import io
import json
import os
import re
import signal
import time
from datetime import date
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

PROVISIONS = {
    "blue-cross-personal", "blue-cross-business",
    "hartford-personal", "hartford-business",
    "all-state-personal", "all-state-business",
}
REQUIRED = ["record_type", "first_name", "last_name", "email", "phone",
            "consent_email", "consent_sms"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+1\d{10}$")
BOOLS = {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}

REGION = os.environ.get("AWS_REGION", "us-east-1")
QUEUE_URL = os.environ.get("QUEUE_URL", "")
MAX_AUTO_ROWS = int(os.environ.get("MAX_AUTO_ROWS", "5000"))

s3 = boto3.client("s3", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)

running = True


def stop(*_):
    global running
    running = False
    log("shutdown requested, finishing current message")


signal.signal(signal.SIGTERM, stop)


def log(msg, **fields):
    print(json.dumps({"msg": msg, **fields}), flush=True)


def member_prefix(provision):
    carrier, lob = provision.rsplit("-", 1)
    return f"{carrier[:2].upper()}{lob[0].upper()}"


def short_hash(*parts):
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12].upper()


def iso_date(value, field):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD")


def validate(row):
    """Return a clean dict or raise ValueError with every problem found."""
    errors = [f"{f} is required" for f in REQUIRED if not (row.get(f) or "").strip()]
    if errors:
        raise ValueError("; ".join(errors))

    rec = {k: (v or "").strip() for k, v in row.items() if k}
    rec["record_type"] = rec["record_type"].lower()
    rec["email"] = rec["email"].lower()

    if rec["record_type"] not in ("lead", "member"):
        errors.append("record_type must be lead or member")
    if not EMAIL_RE.match(rec["email"]):
        errors.append("email is not valid")
    if not PHONE_RE.match(rec["phone"]):
        errors.append("phone must look like +15555550123")
    for f in ("consent_email", "consent_sms"):
        if rec[f].lower() not in BOOLS:
            errors.append(f"{f} must be true/false")
        else:
            rec[f] = BOOLS[rec[f].lower()]

    try:
        if rec["record_type"] == "member":
            if not rec.get("enrolled_date"):
                errors.append("enrolled_date is required for members")
            else:
                rec["enrolled_date"] = iso_date(rec["enrolled_date"], "enrolled_date")
        rec["received_date"] = (iso_date(rec["received_date"], "received_date")
                                if rec.get("received_date") else date.today().isoformat())
    except ValueError as e:
        errors.append(str(e))

    if errors:
        raise ValueError("; ".join(errors))
    return rec


def to_item(rec, provision):
    carrier, lob = provision.rsplit("-", 1)
    base = {
        "first_name": rec["first_name"], "last_name": rec["last_name"],
        "email": rec["email"], "phone": rec["phone"],
        "consent_email": rec["consent_email"], "consent_sms": rec["consent_sms"],
        "carrier": carrier, "line_of_business": lob,
        "source": rec.get("source") or "data_feed",
    }
    if rec["record_type"] == "lead":
        return "leads", "lead_id", {
            **base,
            "lead_id": f"LD-{short_hash(provision, rec['email'])}",
            "lead_status": "new",
            "received_date": rec["received_date"],
        }
    return "members", "member_id", {
        **base,
        "member_id": f"{member_prefix(provision)}-F{short_hash(provision, rec['email'])}",
        "status": "active",
        "enrolled_date": rec["enrolled_date"],
        "onboarding_stage": "day0",
    }


def move(bucket, src, dst):
    s3.copy_object(Bucket=bucket, Key=dst, CopySource={"Bucket": bucket, "Key": src})
    s3.delete_object(Bucket=bucket, Key=src)


def process_file(bucket, key):
    parts = key.split("/")
    name = parts[-1]
    provision = parts[1] if len(parts) == 3 else ""
    if provision not in PROVISIONS:
        move(bucket, key, f"rejected/unknown/{name}")
        log("rejected file: folder is not a known provision", key=key)
        return

    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(body)))

    if len(rows) > MAX_AUTO_ROWS:
        move(bucket, key, f"pending-approval/{provision}/{name}")
        log("held for approval", key=key, rows=len(rows), limit=MAX_AUTO_ROWS)
        return

    tables = {
        "leads": dynamodb.Table(f"{provision}-leads"),
        "members": dynamodb.Table(f"{provision}-members"),
    }
    counts = {"leads": 0, "members": 0, "duplicates": 0, "rejected": 0}
    rejects, seen = [], set()

    for line, row in enumerate(rows, start=2):  # line 1 is the header
        try:
            rec = validate(row)
        except ValueError as e:
            rejects.append({**row, "line": line, "error": str(e)})
            counts["rejected"] += 1
            continue

        kind, pk, item = to_item(rec, provision)
        if item[pk] in seen:
            counts["duplicates"] += 1
            continue
        seen.add(item[pk])
        try:
            tables[kind].put_item(Item=item, ConditionExpression=f"attribute_not_exists({pk})")
            counts[kind] += 1
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                counts["duplicates"] += 1
            else:
                raise

    if rejects:
        out = io.StringIO()
        fields = list(rows[0].keys()) + ["line", "error"]
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rejects)
        s3.put_object(Bucket=bucket, Key=f"rejected/{provision}/{name[:-4]}-rejects.csv",
                      Body=out.getvalue().encode())

    move(bucket, key, f"processed/{provision}/{name}")
    log("feed processed", key=key, provision=provision, rows=len(rows), **counts)


def handle(message):
    body = json.loads(message["Body"])
    if body.get("Event") == "s3:TestEvent":  # sent once when the notification is created
        return
    for record in body.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        process_file(bucket, key)


def main():
    log("intake worker started", queue=QUEUE_URL, max_auto_rows=MAX_AUTO_ROWS)
    while running:
        resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1, WaitTimeSeconds=20)
        for message in resp.get("Messages", []):
            try:
                handle(message)
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])
            except Exception as e:  # leave it on the queue; after 5 tries it goes to the DLQ
                log("failed to process message, will retry", error=str(e))
                time.sleep(2)


if __name__ == "__main__":
    main()

