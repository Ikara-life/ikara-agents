"""
Google Sheets writer — pushes lead data to a Google Spreadsheet.

Setup:
  1. Enable Google Sheets API + Google Drive API in Google Cloud Console
  2. Create a Service Account and download credentials.json
  3. Share your sheet with the service account email (Editor access)
  4. Set SPREADSHEET_ID in config.py

Install: pip install gspread google-auth
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)

COLUMNS = [
    "name",
    "instagram_handle",
    "instagram_url",
    "website",
    "email",
    "phone",
    "address",
    "category",
    "followers",
    "bio",
    "source",
    "facebook_url",
    "scraped_at",
]

HEADER_ROW = [c.replace("_", " ").title() for c in COLUMNS]


class GoogleSheetsWriter:
    def __init__(self, credentials_file: str, spreadsheet_id: str, sheet_name: str):
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self._client = None
        self._sheet = None

    def _connect(self):
        """Lazy connection to Google Sheets."""
        if self._sheet:
            return

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(
                self.credentials_file, scopes=scopes
            )
            self._client = gspread.authorize(creds)
            spreadsheet = self._client.open_by_key(self.spreadsheet_id)

            # Get or create the target sheet tab
            try:
                self._sheet = spreadsheet.worksheet(self.sheet_name)
            except gspread.WorksheetNotFound:
                self._sheet = spreadsheet.add_worksheet(
                    title=self.sheet_name, rows=5000, cols=len(COLUMNS)
                )

            log.info(f"Connected to Google Sheets: '{self.sheet_name}'")

        except ImportError:
            raise ImportError(
                "Missing packages. Run: pip install gspread google-auth"
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_file}\n"
                "Download it from Google Cloud Console → Service Accounts → Keys"
            )

    def write(self, leads: list[dict]):
        """
        Write leads to Google Sheets.
        - Creates header row if sheet is empty
        - Appends new rows below existing data
        - Skips leads already present (matched by email or Instagram handle)
        """
        if not leads:
            log.warning("No leads to write.")
            return

        self._connect()

        # Check if header exists
        existing = self._sheet.get_all_values()
        if not existing:
            self._sheet.append_row(HEADER_ROW, value_input_option="RAW")
            existing_emails = set()
            existing_handles = set()
        else:
            # Build sets of already-written emails + handles to avoid dupes
            try:
                email_col = COLUMNS.index("email")
                handle_col = COLUMNS.index("instagram_handle")
                existing_emails = {
                    row[email_col].lower()
                    for row in existing[1:]
                    if len(row) > email_col and row[email_col]
                }
                existing_handles = {
                    row[handle_col].lower()
                    for row in existing[1:]
                    if len(row) > handle_col and row[handle_col]
                }
            except (ValueError, IndexError):
                existing_emails = set()
                existing_handles = set()

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows_to_add = []
        skipped = 0

        for lead in leads:
            email = (lead.get("email") or "").lower()
            handle = (lead.get("instagram_handle") or "").lower()

            if (email and email in existing_emails) or \
               (handle and handle in existing_handles):
                skipped += 1
                continue

            row = []
            for col in COLUMNS:
                if col == "scraped_at":
                    row.append(now)
                else:
                    val = lead.get(col, "")
                    row.append(str(val) if val is not None else "")
            rows_to_add.append(row)

            if email:
                existing_emails.add(email)
            if handle:
                existing_handles.add(handle)

        if rows_to_add:
            # Batch write for efficiency
            self._sheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
            log.info(f"Wrote {len(rows_to_add)} new leads to Google Sheets "
                     f"(skipped {skipped} duplicates)")
        else:
            log.info(f"All {len(leads)} leads already exist in sheet — nothing new to write.")

    def get_spreadsheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
