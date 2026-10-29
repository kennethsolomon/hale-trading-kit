#!/usr/bin/env python3
"""Local trade journal server. Serves index.html and a JSON API over trades.csv.

Run: python3 journal/app.py [--port 8765] [--no-browser]
Binds to 127.0.0.1 only. Python 3 standard library only.
"""

import argparse
import csv
import json
import os
import re
import stat
import sys
import tempfile
import threading
import traceback
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
JOURNAL_DIR = Path(__file__).resolve().parent
CSV_PATH = JOURNAL_DIR / "trades.csv"
INDEX_PATH = JOURNAL_DIR / "index.html"
MAX_BODY_BYTES = 64 * 1024
MAX_FIELD_CHARS = 4000

COLUMNS = [
    "date_pht", "pair", "timeframe", "side", "market", "leverage",
    "liquidation_price", "setup", "grade", "entry", "stop", "targets", "size",
    "fees_funding", "mode", "research", "result_r", "notes", "mistake_tag",
]
REQUIRED_ENUMS = {
    "side": {"long", "short"},
    "market": {"spot", "perps"},
    "mode": {"paper", "live"},
    "research": {"yes", "no"},
}
OPTIONAL_ENUMS = {"grade": {"A", "B", "C"}}
NUMERIC = {"leverage", "liquidation_price", "entry", "stop", "size", "fees_funding", "result_r"}
PERPS_ONLY = {"leverage", "liquidation_price", "fees_funding"}
MULTILINE = {"notes"}
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}( [0-9]{2}:[0-9]{2})?")
NUMBER_RE = re.compile(r"-?[0-9]+(\.[0-9]+)?")
CONTENT_LENGTH_RE = re.compile(r"[0-9]+")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
WRITE_LOCK = threading.Lock()
POSITIVE = {"liquidation_price", "entry", "stop"}
MAX_LEVERAGE = 125
DEFAULT_CSV_MODE = 0o644
ROW_PATH_RE = re.compile(r"^/api/trades/(\d+)$")


class ApiError(Exception):
    def __init__(self, status, error, detail, field=None):
        super().__init__(f"{error}: {detail}")
        self.status = status
        self.error = error
        self.detail = detail
        self.field = field


class CsvFormatError(Exception):
    pass


def escape_cell(col, value):
    if col not in NUMERIC and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def unescape_cell(col, value):
    if col not in NUMERIC and value.startswith("'") and value[1:].startswith(FORMULA_PREFIXES):
        return value[1:]
    return value


def read_rows():
    try:
        with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if header != COLUMNS:
                raise CsvFormatError(f"{CSV_PATH} header does not match expected columns. Found: {header}")
            rows = []
            for line_no, values in enumerate(reader, start=2):
                if not values:
                    continue
                if len(values) != len(COLUMNS):
                    raise CsvFormatError(
                        f"{CSV_PATH} line {line_no} has {len(values)} fields, expected {len(COLUMNS)}"
                    )
                rows.append({col: unescape_cell(col, v) for col, v in zip(COLUMNS, values)})
            return rows
    except FileNotFoundError:
        raise CsvFormatError(f"{CSV_PATH} is missing. Restart the server to recreate it with the header row.") from None
    except UnicodeDecodeError as exc:
        raise CsvFormatError(f"{CSV_PATH} is not valid UTF-8: {exc}") from None
    except csv.Error as exc:
        raise CsvFormatError(f"{CSV_PATH} could not be parsed as CSV: {exc}") from None


def ensure_csv():
    if not CSV_PATH.exists():
        CSV_PATH.write_text(",".join(COLUMNS) + "\n", encoding="utf-8")
        os.chmod(CSV_PATH, DEFAULT_CSV_MODE)
        print(f"Created {CSV_PATH} with the header row.", flush=True)


def write_rows(rows):
    try:
        mode = stat.S_IMODE(os.stat(CSV_PATH).st_mode)
    except FileNotFoundError:
        mode = DEFAULT_CSV_MODE
    fd, tmp_name = tempfile.mkstemp(prefix=".trades-", suffix=".csv.tmp", dir=JOURNAL_DIR)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(COLUMNS)
            for row in rows:
                writer.writerow([escape_cell(col, row[col]) for col in COLUMNS])
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, CSV_PATH)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def coerce_text(field, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"{field} must be a string", field)
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"{field} must be a string", field)
    return value


def validate_row(payload, name="row"):
    if not isinstance(payload, dict):
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_body", f"'{name}' must be an object", name)
    unknown = sorted(set(payload) - set(COLUMNS))
    if unknown:
        raise ApiError(
            HTTPStatus.UNPROCESSABLE_ENTITY, "unknown_field",
            f"Unknown column(s): {', '.join(unknown)}", unknown[0],
        )
    row = {}
    for col in COLUMNS:
        value = coerce_text(col, payload.get(col)).strip()
        if len(value) > MAX_FIELD_CHARS:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"{col} exceeds {MAX_FIELD_CHARS} characters", col)
        if col not in MULTILINE and ("\n" in value or "\r" in value):
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"{col} must be a single line", col)
        row[col] = value

    date_error = ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"date_pht must be a real date as YYYY-MM-DD or YYYY-MM-DD HH:MM (got '{row['date_pht']}')", "date_pht")
    if not DATE_RE.fullmatch(row["date_pht"]):
        raise date_error
    try:
        datetime.strptime(row["date_pht"], "%Y-%m-%d %H:%M" if " " in row["date_pht"] else "%Y-%m-%d")
    except ValueError:
        raise date_error from None
    if not row["pair"]:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", "pair is required", "pair")
    for col in ("entry", "stop"):
        if not row[col]:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"{col} is required", col)
    row["pair"] = row["pair"].upper()

    for col, allowed in REQUIRED_ENUMS.items():
        if row[col] not in allowed:
            raise ApiError(
                HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field",
                f"{col} must be one of: {', '.join(sorted(allowed))} (got '{row[col]}')", col,
            )
    for col, allowed in OPTIONAL_ENUMS.items():
        if row[col] and row[col] not in allowed:
            raise ApiError(
                HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field",
                f"{col} must be empty or one of: {', '.join(sorted(allowed))} (got '{row[col]}')", col,
            )
    for col in NUMERIC:
        if not row[col]:
            continue
        if not NUMBER_RE.fullmatch(row[col]):
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"{col} must be a plain decimal like 12 or -1.5, or empty (got '{row[col]}')", col)
        number = float(row[col])
        if col == "leverage" and not 0 < number <= MAX_LEVERAGE:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"leverage must be above 0 and at most {MAX_LEVERAGE} (got '{row[col]}')", col)
        if col == "size" and number < 0:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"size must be 0 or more (got '{row[col]}')", col)
        if col in POSITIVE and number <= 0:
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field", f"{col} must be above 0 (got '{row[col]}')", col)
    if row["market"] == "spot":
        filled = sorted(col for col in PERPS_ONLY if row[col])
        if filled:
            raise ApiError(
                HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_field",
                f"{filled[0]} only applies to market=perps", filled[0],
            )
    return row


def original_row(payload):
    original = payload.get("original")
    if not isinstance(original, dict):
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_body", "'original' row object is required for update and delete", "original")
    return {col: coerce_text(col, original.get(col)) for col in COLUMNS}


def check_unchanged(rows, index, original):
    if index >= len(rows):
        raise ApiError(HTTPStatus.CONFLICT, "stale_row", f"Row {index} no longer exists. Reload and try again.")
    if rows[index] != original:
        raise ApiError(HTTPStatus.CONFLICT, "stale_row", f"Row {index} changed since it was loaded. Reload and try again.")


class Handler(BaseHTTPRequestHandler):
    server_version = "TradeJournal/1.0"
    timeout = 10

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    def send_json(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, err):
        body = {"error": err.error, "detail": err.detail}
        if err.field:
            body["field"] = err.field
        self.send_json(err.status, body)

    def check_host(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed:
            raise ApiError(HTTPStatus.FORBIDDEN, "forbidden_host", "Requests must target 127.0.0.1 or localhost")

    def read_json(self):
        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";")[0].strip() != "application/json":
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "invalid_content_type", "Content-Type must be application/json")
        length_header = self.headers.get("Content-Length")
        if length_header is None or not CONTENT_LENGTH_RE.fullmatch(length_header):
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "length_required", "A numeric Content-Length header is required")
        length = int(length_header)
        if length > MAX_BODY_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", f"Body is {length} bytes, limit is {MAX_BODY_BYTES}")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json", f"Body is not valid JSON: {exc}") from None
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json", "Body must be a JSON object")
        return payload

    def dispatch(self, method):
        try:
            self.check_host()
            self.route(method)
        except ApiError as err:
            self.send_error_json(err)
        except CsvFormatError as err:
            self.send_error_json(ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "csv_format", str(err)))
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", f"{type(exc).__name__}: {exc}"))

    def route(self, method):
        path = self.path.split("?", 1)[0]
        if method == "GET" and path in ("/", "/index.html"):
            data = INDEX_PATH.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/trades":
            if method == "GET":
                rows = read_rows()
                data = [{"index": i, "row": row} for i, row in enumerate(rows)]
                self.send_json(HTTPStatus.OK, {"data": data, "meta": {"total": len(rows), "columns": COLUMNS}})
                return
            if method == "POST":
                payload = self.read_json()
                row = validate_row(payload.get("row"))
                with WRITE_LOCK:
                    rows = read_rows()
                    rows.append(row)
                    write_rows(rows)
                self.send_json(HTTPStatus.CREATED, {"data": {"index": len(rows) - 1, "row": row}})
                return
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", f"{method} not allowed on {path}")
        match = ROW_PATH_RE.match(path)
        if match:
            index = int(match.group(1))
            if method == "PUT":
                payload = self.read_json()
                original = original_row(payload)
                row = validate_row(payload.get("row"))
                with WRITE_LOCK:
                    rows = read_rows()
                    check_unchanged(rows, index, original)
                    rows[index] = row
                    write_rows(rows)
                self.send_json(HTTPStatus.OK, {"data": {"index": index, "row": row}})
                return
            if method == "DELETE":
                payload = self.read_json()
                original = original_row(payload)
                with WRITE_LOCK:
                    rows = read_rows()
                    check_unchanged(rows, index, original)
                    removed = rows.pop(index)
                    write_rows(rows)
                self.send_json(HTTPStatus.OK, {"data": {"index": index, "row": removed}})
                return
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", f"{method} not allowed on {path}")
        raise ApiError(HTTPStatus.NOT_FOUND, "not_found", f"No route for {method} {path}")

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_DELETE(self):
        self.dispatch("DELETE")


def main():
    parser = argparse.ArgumentParser(description="Local trade journal UI for journal/trades.csv")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    ensure_csv()
    try:
        read_rows()
    except CsvFormatError as err:
        raise SystemExit(str(err)) from None

    # One thread per request so a slow client cannot block others; WRITE_LOCK serializes CSV read-modify-write.
    server = ThreadingHTTPServer((HOST, args.port), Handler)
    server.daemon_threads = True
    url = f"http://{HOST}:{args.port}/"
    print(f"Trade journal running at {url} (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
