"""
Lambda: projecthandler

Env vars:
- TABLE=Projects
- PK_ATTR=Project
- SK_ATTR={createdAtEpochSeconds}#{uuid}
- ALLOWED_ORIGIN=https://<your-cloudfront-domain>   # no trailing slash

IAM (minimum):
- dynamodb:PutItem, dynamodb:Query on arn:aws:dynamodb:<region>:<acct>:table/Projects
"""

import os
import re
import json
import time
import uuid
import base64
import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr

TABLE = os.environ.get("TABLE", "Projects")
PK_ATTR = os.environ.get("PK_ATTR", "pk")
SK_ATTR = os.environ.get("SK_ATTR", "sk")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

ddb = boto3.resource("dynamodb")
table = ddb.Table(TABLE)

GITHUB_REPO_RE = re.compile(
    r"^https?://(www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$"
)

# ---------- helpers ----------

def to_native(x):
    if isinstance(x, list):
        return [to_native(i) for i in x]
    if isinstance(x, dict):
        return {k: to_native(v) for k, v in x.items()}
    if isinstance(x, Decimal):
        return int(x) if (x % 1 == 0) else float(x)
    return x

def resp(status: int, body: dict, origin: str | None = None):
    origin = origin or ALLOWED_ORIGIN
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }

# ---------- handlers ----------

def handle_post(event):
    body_str = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body_str = base64.b64decode(body_str).decode()

    try:
        data = json.loads(body_str or "{}")
    except Exception:
        return resp(400, {"error": "Invalid JSON"})

    repo_url = (data.get("repo_url") or "").strip()
    title = (data.get("title") or "").strip()
    submitter = (data.get("submitter") or "").strip()
    description = (data.get("description") or "").strip()

    m = GITHUB_REPO_RE.match(repo_url)
    if not m:
        return resp(400, {"error": "repo_url must look like https://github.com/<owner>/<repo>"})
    owner, repo = m.group(2), m.group(3)

    now = int(time.time())
    id_ = str(uuid.uuid4())
    sk = f"{now}#{id_}"

    item = {
        PK_ATTR: "PROJECT",
        SK_ATTR: sk,
        "id": id_,
        "repo_url": repo_url,
        "owner": owner,
        "repo": repo,
        "title": title or repo,
        "description": description,
        "submitter": submitter,
        "createdAt": now,
    }
    # helpful duplicates if your attr names differ from pk/sk
    if PK_ATTR != "pk":
        item["pk"] = item[PK_ATTR]
    if SK_ATTR != "sk":
        item["sk"] = item[SK_ATTR]

    table.put_item(Item=item)
    return resp(201, {"ok": True, "id": id_, "createdAt": now})

def handle_get(event):
    params = event.get("queryStringParameters") or {}
    try:
        limit = max(1, min(100, int(params.get("limit") or "50")))
    except Exception:
        limit = 50

    eks = None
    cursor = params.get("cursor")
    if cursor:
        try:
            eks = json.loads(base64.b64decode(cursor).decode())
        except Exception:
            return resp(400, {"error": "Invalid cursor"})

    # Query newest-first by partition key
    qargs = {
        "KeyConditionExpression": Key(PK_ATTR).eq("PROJECT"),
        "Limit": limit,
        "ScanIndexForward": False,  # descending by sort key
    }
    if eks:  # only include if present
        qargs["ExclusiveStartKey"] = eks

    items = []
    next_cursor = None

    try:
        res = table.query(**qargs)
        items = res.get("Items", [])
        if "LastEvaluatedKey" in res:
            next_cursor = base64.b64encode(
                json.dumps(res["LastEvaluatedKey"]).encode()
            ).decode()
    except Exception as e:
        print(f"[DEBUG] Query failed: {e}")

    # Fallback: filtered scan (useful if key names/env mis-match during setup)
    if not items:
        try:
            scan_args = {
                "FilterExpression": Attr(PK_ATTR).eq("PROJECT"),
                "Limit": limit,
            }
            if eks:
                scan_args["ExclusiveStartKey"] = eks
            res = table.scan(**scan_args)
            items = res.get("Items", [])
            # best-effort sort by createdAt desc
            try:
                items.sort(key=lambda x: x.get("createdAt", 0), reverse=True)
            except Exception:
                pass
            if "LastEvaluatedKey" in res:
                next_cursor = base64.b64encode(
                    json.dumps(res["LastEvaluatedKey"]).encode()
                ).decode()
        except Exception as e:
            print(f"[DEBUG] Scan failed: {e}")

    return resp(200, {"items": [to_native(i) for i in items], "next_cursor": next_cursor})

def lambda_handler(event, context):
    method = (event.get("httpMethod") or "GET").upper()
    if method == "OPTIONS":
        return resp(200, {"ok": True})
    if method == "POST":
        return handle_post(event)
    if method == "GET":
        return handle_get(event)
    return resp(405, {"error": "Method not allowed"})
