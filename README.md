# BDE Weekly Productivity Report

## PostgreSQL audit

The report scope is Impacteers Academy (Org 02). The ER notes point to
the `public` schema and organisation ID
`00000000-0000-0000-0000-000000000002`. Treat these as references until
verified. Steps 6–8 list database objects visible to the read-only login.
The inventory can include objects shared by FutureJobs and Academy.
Organisation filters apply later when validating CRM records.

## Run in VS Code

Open the extracted `BDE_Weekly_Report` folder in VS Code and run these
commands in the integrated terminal.

```bash
python -m pip install -r requirements.txt
```

Fill in the placeholder `.env` with your PostgreSQL read-only login.
Keep it local. If your database administrator specifies an SSL mode,
set `DB_SSLMODE` as instructed.

```bash
python audit/01_connection_test.py
python audit/02_schema_audit.py
```

Proceed with the inventory after the connection test reports
`Read only: on`. Both scripts verify the active transaction mode
before running queries. Run the commands from a machine that can
reach the CRM database.

| Step | File in `output/` | Contents |
| --- | --- | --- |
| 6 | `06_schemas.csv` | Schemas visible to the login |
| 7 | `07_tables.csv` | Visible table and view names and types |
| 8 | `08_relevant_tables.csv` | Candidate objects found by keyword |

Share the three CSVs after reviewing the object names for sensitive
information. The inventory queries read PostgreSQL metadata only.
A keyword match identifies a candidate for the next review.

## Next audit

After reviewing the CSVs, inspect one confirmed object at a time.
For example, if the inventory confirms `public.leads`:

```bash
python audit/03_table_columns.py public leads
python audit/03_table_columns.py public --report-tables
```

The second command writes `output/09_report_columns.csv` with column
metadata for the Course team candidates named in the ER notes.

Use the following mapping to choose which objects to inspect. Table names
come from the ER notes and await live verification.

| Report area | Candidate sources | What to verify later |
| --- | --- | --- |
| Employee master | `admin_users` | BDE role, team, active status, working hours |
| Lead management | `leads` | Assigned BDE, creation time, program, current stage |
| Follow-up activity | `lead_activities`, `follow_ups` | Activity owner, lead, event time, completion status |
| Stage history | `lead_audit_logs`, `lead_activities` | Previous stage, new stage, changed by, event timestamp |
| Program and sales | `lead_program_enrollments`, `lead_payments` | Program link, enrolment, payment status, recognised revenue rules |
| Calling performance | Callyzer API, CRM `callyzer_calls` | Call ID, BDE mapping, call time, duration, direction, coverage and sync lag |

Review primary and foreign keys before joining records. Validate sample
records within Org 02 in a later pass. Weekly stage movement requires a
timestamped stage-change event. Compare the CRM call records against the
Callyzer API before choosing the source for hourly calling metrics.

## Generate the Course team HTML report

From the project folder run:

```bash
python build_report.py sample_input.json
```

Open `output/Weekly_Productivity_Report.html` in your browser. The sample is
synthetic. The Impacteers logo loads from the official website. The reporting
dates and drill-downs are contained in the generated file.

To use your own data, supply a complete, normalized JSON export in the
same format as `sample_input.json`. Provide only Course team (Org 02) records.
The builder uses the coverage end date to set the latest and previous
seven-day ranges. Dates are inclusive. Choose a custom range in the HTML
to review a shorter period or to span both presets.

| Input | What to provide |
| --- | --- |
| `coverage` | First and last fully covered dates in IST. Missing days within coverage display zero activity. |
| `bdes` | Unique string ID, name, vertical, and team lead per BDE in scope. |
| `leads` | One row per unique lead received, with recipient BDE, timestamp, and current stage. Hot, Cold, Warm, and Dead/Junk are shown as a breakdown. Other stages still count toward total leads. |
| `calls` | Outbound call attempts with call ID, BDE, timestamp, consistent normalized destination or opaque contact key, connected flag, and actual talk seconds. Identical call IDs are counted once. |
| `daily_crm` | One row per BDE per IST date with follow-ups completed, follow-ups pending as of that day, stage changes, enrolments, and reportable revenue in rupees. |

Use timestamps with an explicit UTC offset. The builder converts them to
IST so call hours and lead dates follow the same calendar. Unique Calls
counts distinct contacts at each selected level. Average Talk Time divides
total talk seconds by connected calls and displays an em dash when no call
connected. Daily Dead/Junk counts leads received that day with that current
status. Customer phone numbers, contact keys, and call IDs are excluded from
the generated HTML.

The database audit and report generation can run independently. Live extraction
from PostgreSQL and any Callyzer source needs the verified Org 02 table and
field mapping, including call outcomes, talk-time units, assignment ownership,
stage history, and the revenue eligibility rules.

## Fetch Callyzer calls directly

The `.env` includes separate PostgreSQL and Callyzer settings. Set
`CALLYZER_API_TOKEN` locally using the token for your Callyzer account.
The default base URL is production. For a sandbox credential, set
`CALLYZER_API_BASE_URL=https://sandbox.api.callyzer.co/api/v2.3/`.
The production API requires the Callyzer API add-on. See the
[official Callyzer developer documentation](https://developers.callyzer.co/).

In your normalized CRM input, add `callyzer_number` to each BDE under
`bdes`, in countrycode-number format such as `91-9000000000`. This maps
the registered Callyzer employee number to the CRM BDE ID. Keep the
staff mapping local. Set `CALLYZER_ACCOUNT_TIMEZONE` to match the
Callyzer account so returned call dates can be converted to IST.

```bash
python -m pip install -r requirements.txt
python build_report.py course_crm_export.json --fetch-callyzer
```

The flag fetches outbound calls for the mapped BDEs and coverage dates
and replaces the input's `calls` list for this run. By default it uses
PhoneCall and Voice. Set `CALLYZER_CALL_METHOD=WhatsAppCall` to report
WhatsApp instead. Callyzer classifies calls longer than two seconds as
connected. The HTML includes the resulting totals and hourly breakdowns.
A regular run without the flag uses the input's existing `calls` list.
The normalized CRM export still supplies BDEs, leads, and daily CRM metrics.

## Course team hierarchy and database roles

`team_hierarchy.json` records the user-provided Org 02 hierarchy. Sales persons
are labelled **BDEs**. Database tags reported by the user are `sales person`,
`team lead`, `org admin`, and `admin`; exact stored values and user IDs still
need live verification. A manager's database tag must not be inferred from
their management position. Admin tags alone do not identify a BDE.

The report does not display the team hierarchy. Its vertical performance table
uses Govt Central (Dilip Kumar; RRB, SSC and Banking), Govt State
(Keerthivengatesh; TNPSC), and Tech (Akshay). Sample metrics remain synthetic
and are not assigned to named staff. The local team mapping is not a database
update or a verified CRM mapping.

## Live report: 9–15 November 2026 IST

The dated deliverable is
`output/Weekly_Productivity_Report_2026-11-09_to_2026-11-15.html`.
The default HTML is also updated. Snapshot inputs and reconciliation are in
`output/live_2026-11-09_2026-11-15/`; these local files contain private CRM and
call data. The HTML omits lead IDs, call IDs and phone numbers.

Regenerate from this saved snapshot:

```bash
python3 normalize_weekly_live.py --start 2026-11-09 --end 2026-11-15
python3 build_report.py output/live_2026-11-09_2026-11-15/normalized_input.json
```

`extract_weekly_live.py` retrieves the fixed reporting window and reuses existing
snapshot files; it is not a live refresh of an existing snapshot. The user/team,
follow-up and Callyzer employee snapshots were fetched separately for this run.
The report covers the 15 requested BDEs, including the approved name-based
Callyzer mappings. Its Data basis section documents assignment-date/current-owner
semantics, enrollment-date limitations and unavailable revenue, pending-task
history and stage-change counts. Zero completed tasks means zero returned task
completions in this week, not zero follow-up calls or other activity.

## Last seven completed days: 11–17 November 2026 IST

The latest deliverable is `output/Weekly_Productivity_Report.html`, also saved as
`output/Weekly_Productivity_Report_2026-11-11_to_2026-11-17.html`.
The period excludes the current incomplete day, 18 November.

```bash
python3 extract_weekly_live.py --start 2026-11-11 --end 2026-11-17
python3 normalize_weekly_live.py --start 2026-11-11 --end 2026-11-17
python3 build_report.py output/live_2026-11-11_2026-11-17/normalized_input.json
```

The extractor now fetches the supporting user, team, stage, follow-up and employee
directories itself. Existing lead/call snapshots are reused for the same period.
Use the explicit Back button to return from daily detail to the BDE view, from
the BDE view to its overview, or from a filtered overview to all verticals.

## September–November report with date filters

Current coverage is 1 September–18 November 2026 IST, through the displayed
extraction cutoff. The latest artifact is `output/Weekly_Productivity_Report.html`
and the dated copy is `output/Productivity_Report_2026-09-01_to_2026-11-18.html`.
The full available range opens by default. Last 1 day means 18 November (today
at extraction); Last 7 days means 12–18 November inclusive. Custom dates must
fall within the snapshot coverage. These presets do not fetch new data.

```bash
python3 extract_weekly_live.py --start 2026-09-01 --end 2026-11-18
python3 normalize_weekly_live.py --start 2026-09-01 --end 2026-11-18
python3 build_report.py output/live_2026-09-01_2026-11-18/normalized_input.json
```

The explanatory Data basis section is removed from the report at the user's
request; methodology remains in the normalized input's source_notes. The short
table notes retain the assignment/current-owner basis and unavailable-value
meaning. CRM snapshot provenance is saved in the period's snapshot directory.
Callyzer calls are retrieved in seven-day batches with completion and duplicate
checks. Existing saved batches are reused when rerunning the same extraction.

## Corrected lead metric

Leads received now counts distinct leads by CRM `createdAt`, converted to IST,
within the selected dates. `assignedAt` is not used. The 15-person scope remains
unchanged; BDE attribution uses the current `assignedToId`, not ownership at
creation. Lead stage breakdowns use the same created-date cohort and current
stages. Presets are relative to the latest available snapshot date, not the
computer's current date.

## Refresh through 19 November 2026

The current report uses CRM `createdAt` (IST) for Leads received, with current
BDE ownership. The default extraction and normalization end date now uses
today's IST date; the start defaults to 1 September 2026. After this refresh,
Last 7 days is 13–19 November and Last 1 day is 19 November up to extraction.
The dated artifact is `output/Productivity_Report_2026-09-01_to_2026-11-19.html`.
The default `output/Weekly_Productivity_Report.html` is regenerated as well.
