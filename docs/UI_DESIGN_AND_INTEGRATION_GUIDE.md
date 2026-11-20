# ServerGen AI — Enterprise UI Design & Integration Guide
**Version:** 2.4.0  
**Status:** Approved for Production Integration  
**Classification:** Internal Technical Architecture & UI Engineering Manual  

---

## Executive Summary

This specification provides the end-to-end design system, visual specifications, component architectures, REST API contracts, and integration workflows for the **ServerGen AI Front-End Ecosystem**. Specifically, it covers the user interface integration for the two new enterprise features:

1. **Enterprise Automated Notification Subsystem** — Event-driven notification center with role-based dispatching, category visual badging, unread counters, in-app notification dropdown, and user preference controls.
2. **Natural Language Data Analysis Workbench** — Safe, prompt-driven spreadsheet analytics interface allowing business users and managers to query complex multi-sheet Excel (.xlsx, .xls) and CSV datasets using ordinary English, backed by deterministic Python calculation engines, interactive SVG visualizations, and Ollama Llama 3.2 3B executive narrative synthesis.

---

## 1. Design System & Design Tokens

ServerGen AI adheres to an executive, zero-trust enterprise design language engineered for clarity, rapid situational awareness, and high-contrast accessibility.

### 1.1 Color Palette & Semantic Tokens

| Token Name | Hex Code | Semantic Role | Usage Context |
| :--- | :--- | :--- | :--- |
| `--bg-base` | `#F8FAFC` | Slate 50 | Base application workspace background |
| `--bg-surface` | `#FFFFFF` | White | Cards, modal sheets, popovers, dropdown containers |
| `--bg-elevated` | `#F1F5F9` | Slate 100 | Table headers, secondary toolbars, chip backgrounds |
| `--border-subtle` | `#E2E8F0` | Slate 200 | Dividers, card borders, subtle grid lines |
| `--border-default`| `#CBD5E1` | Slate 300 | Standard input borders, active panel outlines |
| `--border-focus` | `#0284C7` | Sky 600 | Active focus rings, selected state highlights |
| `--primary` | `#0284C7` | Sky 600 | Primary CTA buttons, active navigation, direct accents |
| `--primary-hover`| `#0369A1` | Sky 700 | Interactive hover state for primary elements |
| `--primary-glow` | `rgba(2,132,199,0.15)` | Sky Glow | Focus glow, active tab backdrop glow |
| `--success` | `#16A34A` | Emerald 600 | Analytics success, positive variance, approval badge |
| `--warning` | `#D97706` | Amber 600 | Pending manager approval, warning alerts, outliers |
| `--danger` | `#DC2626` | Rose 600 | Policy violations, security blocks, budget deficits |
| `--purple` | `#7C3AED` | Violet 600 | AI orchestration, intent parsing, machine intelligence |
| `--text-primary` | `#0F172A` | Slate 900 | High-contrast body text, headings, KPIs |
| `--text-secondary`| `#334155` | Slate 700 | Subtitles, label descriptions, table body text |
| `--text-muted` | `#64748B` | Slate 500 | Timestamps, metadata, inactive state labels |

### 1.2 Typography Hierarchy

- **Primary Sans Font**: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- **Monospace Code Font**: `'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace`

```css
/* Typography Scale */
--text-xs:   0.68rem; /* 11px - Badge counters, timestamps */
--text-sm:   0.78rem; /* 12.5px - Secondary labels, chip pills */
--text-base: 0.88rem; /* 14px - Primary body text, table cells */
--text-md:   1.00rem; /* 16px - Card subheadings, modal titles */
--text-lg:   1.15rem; /* 18.5px - Feature headers, panel titles */
--text-xl:   1.50rem; /* 24px - Dashboard KPI summaries */
--text-2xl:  1.85rem; /* 30px - Executive metric hero values */
```

### 1.3 Depth & Elevation Tokens

```css
--shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.03);
--shadow-popover: 0 14px 35px -5px rgba(0, 0, 0, 0.12), 0 8px 12px -6px rgba(0, 0, 0, 0.08);
```

---

## 2. Navigation Architecture & Role-Adaptive Layout

ServerGen AI utilizes an asynchronous executive master shell divided into four primary layout planes:

```
+---------------------------------------------------------------------------------------------------------+
| [LOGO] ServerGen AI | Enterprise Zero-Trust AI | [QUICK ROLE: Admin|Mgr|Analyst|Op|Emp] | [BELL] [USER] [LOGOUT]|
+---------------------------------------------------------------------------------------------------------+
| LIVE TELEMETRY: (•) API Server: Connected | (•) Database: Connected | (•) Ollama Llama 3.2: 3B: Ready   |
+----------------------+----------------------------------------------------------------------------------+
| NAVIGATION RAIL      | MAIN WORKSPACE CANVAS                                                            |
|                      |                                                                                  |
| > AI Operations Hub  | [FEATURE WORKBENCH]                                                              |
| > Manager Cockpit    |                                                                                  |
| > Document Vaults    | - Document & Sheet Schema Selector                                               |
| > Audit & Governance | - Smart Suggested Question Pills                                                 |
| > Slide & Doc Studio | - Natural Language Prompt Input Bar                                              |
| > Spreadsheet Studio | - Direct Answer Callout + Executive AI Narrative Card                            |
| > System Health      | - Interactive SVG Visualization & Filterable Data Table                          |
|                      | - 1-Click Deliverable Export Toolbar (.xlsx, .pdf, .pptx)                        |
+----------------------+----------------------------------------------------------------------------------+
```

### 2.1 Role-Based Adaptive Visibility Rules

| Role | Navigation Clearance | Notification Categories | Role Vault Clearance |
| :--- | :--- | :--- | :--- |
| **Administrator** | Full system visibility (Security, Users, Audit, Config) | Security, Approvals, All Documents | `restricted`, `confidential`, `internal`, `public` |
| **Manager** | Manager Cockpit, Approvals, Analytics, RAG, Spreadsheets | Pending Approvals, High-Cost Analytics | `confidential`, `internal`, `public` |
| **Security Analyst**| Audit Logs, Security Telemetry, DLP Redactions | Security Violations, Vault Intrusion | `confidential`, `internal`, `public` |
| **IT Operator** | System Health, Resource Telemetry, Task Runner | Service Status, Execution Failures | `internal`, `public` |
| **Employee** | Document Search, Spreadsheets, Personal History | My Decisions, Upload Finished | `internal`, `public` |

---

## 3. Component Specification: Enterprise Notification Center

### 3.1 Visual Anatomy & Layout

The Notification Center is located in the top-right header plane, directly left of the User Identity Pill.

```
       +---------------------------------------------+
       | Notifications [ 3 unread ]   [Mark all read]|
       +---------------------------------------------+
(•) -> | [!] Approval Required: Financial Spend      |
       |     Manager clearance needed: >$10k export  |
       |     2 mins ago                              |
       +---------------------------------------------+
(•) -> | [Doc] Document Indexed Successfully         |
       |     'Q3_Regional_Budget.xlsx' in Vault      |
       |     14 mins ago                             |
       +---------------------------------------------+
       | [AI] Spreadsheet Analytics Complete         |
       |     Outlier analysis found 3 anomalies      |
       |     1 hour ago                              |
       +---------------------------------------------+
       | Enterprise Event Stream       [Preferences] |
       +---------------------------------------------+
```

### 3.2 Visual Badges & Category Matrix

| Category | Primary Icon | Icon Background | Icon Color | Event Trigger Sources |
| :--- | :--- | :--- | :--- | :--- |
| `approval` | `<i class="fa-solid fa-signature">` | `#FEF3C7` (Amber 100) | `#D97706` (Amber 600) | `approval_service.py`: Request created, Manager approved, Manager rejected |
| `document` | `<i class="fa-solid fa-file-circle-check">` | `#E0F2FE` (Sky 100) | `#0284C7` (Sky 600) | `rag/service.py`: Document ingestion indexed, Vault assignment, Extraction failed |
| `security` | `<i class="fa-solid fa-shield-triangle-exclamation">` | `#FEE2E2` (Rose 100) | `#DC2626` (Rose 600) | `orchestrator/engine.py`: Zero-trust DLP block, Role-vault 403 denied |
| `analytics`| `<i class="fa-solid fa-chart-line">` | `#DCFCE7` (Emerald 100) | `#16A34A` (Emerald 600) | `spreadsheets.py`: Spreadsheet parsed, NL analysis finished, Deliverable built |

### 3.3 Event Lifecycle & Frontend Architecture

1. **Badge Polling**: Background timer polls `GET /api/v1/notifications/unread-count` every 15 seconds. If `unread_count > 0`, the badge displays with CSS pulse animation.
2. **Flyout Open**: Clicking the bell triggers `toggleNotificationDropdown()`, fetching `GET /api/v1/notifications?limit=25` and displaying cards ordered by timestamp descending.
3. **Item Read**: Clicking an individual notification item executes `PATCH /api/v1/notifications/{id}/read`. The unread dot vanishes, the background changes from light sky `#F0F9FF` to neutral white, and the badge counter decrements.
4. **Mark All Read**: Clicking `[Mark all read]` executes `POST /api/v1/notifications/read-all`, instantaneously clearing all unread markers and hiding the counter badge.
5. **Preferences Modal**: Clicking `[Preferences]` opens `#notif-pref-modal` with category checkboxes (`notify_approvals`, `notify_documents`, `notify_security`, `notify_analytics`) and channel toggles (`in_app_enabled`, `email_enabled`).

---

## 4. Component Specification: Natural Language Data Analysis Workbench

The Natural Language Data Analysis Workbench enables managers and business users to interact with enterprise spreadsheets without writing formulas, SQL, or code.

### 4.1 Component Architecture Diagram

```mermaid
flowchart TD
    User([User in UI]) -->|1. Select Document| DocSelect[Document & Sheet Selector]
    DocSelect -->|Fetch Schema Profile| SchemaAPI[GET /spreadsheets/:id/schema]
    SchemaAPI -->|Columns, Types, Questions| SchemaCard[Schema Inspector & Suggested Chips]
    
    User -->|2. Click Chip or Type Query| NLInput[Natural Language Input Bar]
    NLInput -->|POST /spreadsheets/nl-query| APIEndpoint[FastAPI Endpoint]
    
    subgraph Backend Engine
        APIEndpoint --> RBAC[Role Vault Clearance Check]
        RBAC --> IntentParser[Intent & Column Parser]
        IntentParser --> SafeExecution[Deterministic Python Engine\nNo eval / No SQL]
        SafeExecution --> Ollama[Ollama Llama 3.2 3B\nExecutive Synthesis]
        SafeExecution --> HistoryDB[(Analysis History DB)]
    end
    
    Ollama -->|JSON Response| UIWorkbench[Results View]
    
    subgraph UI Workbench Presentation
        UIWorkbench --> DirectAnswer[Direct Answer Callout Card]
        UIWorkbench --> AINarrative[Executive AI Narrative Explanation]
        UIWorkbench --> SVGChart[Interactive SVG Bar/Line Chart]
        UIWorkbench --> DataTable[Filterable Tabular Data View]
        UIWorkbench --> ExportBar[1-Click Export: XLSX | PDF | PPTX]
    end
```

### 4.2 Interactive Sub-Components

#### A. Document & Sheet Selector Bar
- **File Dropdown**: Lists all uploaded `.xlsx`, `.xls`, and `.csv` files accessible within the active user's role vault clearance.
- **Worksheet Dropdown**: Populated dynamically with all sheets (e.g. `Sheet1`, `Q3_Actuals`, `Regional_Breakdown`).
- **Role Vault Badge**: Displays the current clearance level (`CONFIDENTIAL`, `RESTRICTED`, `INTERNAL`, `PUBLIC`).

#### B. Schema Profile Inspector
- Renders each column as an interactive pill with data type tags:
  - Numeric: `<span class="nl-badge-type nl-type-number">number</span>`
  - Text: `<span class="nl-badge-type nl-type-string">string</span>`
  - Date: `<span class="nl-badge-type nl-type-date">date</span>`
- Displays row count and missing/null counts for complete audit transparency.

#### C. Smart Suggested Question Chips
The system automatically generates domain-specific questions matching the 6 supported analytical operations:

```html
<div class="nl-suggested-chips-container">
    <button class="nl-chip-btn" onclick="applyNlQuestion('Calculate the total expenditure across all departments')">
        <i class="fa-solid fa-calculator text-primary"></i> Total Expenditure
    </button>
    <button class="nl-chip-btn" onclick="applyNlQuestion('Show the top 5 departments based on expenditure')">
        <i class="fa-solid fa-ranking-star text-warning"></i> Top 5 by Expenditure
    </button>
    <button class="nl-chip-btn" onclick="applyNlQuestion('Which departments exceeded their allocated budgets?')">
        <i class="fa-solid fa-scale-balanced text-danger"></i> Budget Overruns
    </button>
    <button class="nl-chip-btn" onclick="applyNlQuestion('Detect outliers and abnormal values in amount')">
        <i class="fa-solid fa-triangle-exclamation text-warning"></i> Outlier Detection
    </button>
    <button class="nl-chip-btn" onclick="applyNlQuestion('Find all duplicate records in this spreadsheet')">
        <i class="fa-solid fa-clone text-purple"></i> Find Duplicates
    </button>
    <button class="nl-chip-btn" onclick="applyNlQuestion('Show the monthly trend for expenditure')">
        <i class="fa-solid fa-chart-line text-success"></i> Monthly Trend
    </button>
</div>
```

#### D. Direct Answer & Executive AI Narrative
- **Direct Answer**: Emerald callout card containing the definitive, single-sentence response calculated deterministically (e.g., *"Total Expenditure across 4 departments is $1,780,000.00"* or *"1 department (Security) exceeded allocated budget by $30,000.00"*).
- **Executive Narrative**: Slate-surface card synthesizing key takeaways, context, and managerial insights grounded exclusively on the calculated figures.

#### E. Interactive SVG Visualizations
The UI dynamically renders responsive, pure SVG vector charts without external charting library dependencies:
- **Bar Charts**: Group-by comparisons, ranking, category totals, and budget vs. actual variances.
- **Line Charts**: Monthly and quarterly trend analysis with markers and gridlines.
- **Outlier Scatters**: Statistical IQR distribution with upper/lower fence threshold indicators.

#### F. Filterable Tabular Data Grid
- Clean, high-density HTML table displaying all records or aggregated summaries.
- Tabular figures use font feature settings `tabular-nums` for precise vertical alignment.
- Handles pagination and truncation gracefully when datasets exceed 100 rows.

#### G. Query History Drawer
- Preserves the chronological stream of questions asked by the user against the document.
- Clicking any historical query immediately restores the question and re-runs or inspects the calculated output.

---

## 5. REST API Client Contracts & Specifications

### 5.1 Notification Subsystem Endpoints

#### 1. `GET /api/v1/notifications`
- **Description**: List notifications for the authenticated user.
- **Query Parameters**:
  - `limit` (integer, default: 20)
  - `unread_only` (boolean, default: false)
  - `category` (string, optional: `approval`, `document`, `security`, `analytics`)
- **Response `200 OK`**:
```json
[
  {
    "id": "e4b2d398-3bf2-45e8-b76f-8dc8c34f2d01",
    "user_id": "c1f76d9e-e8b2-4d0f-a49b-73a71b1ff048",
    "title": "Approval Required: High-Risk Service Restart",
    "message": "IT Operations requested emergency cold restart of production database.",
    "category": "approval",
    "severity": "warning",
    "is_read": false,
    "action_url": "/approvals/e4b2d398",
    "metadata_json": "{\"task_id\": \"task-9912\"}",
    "created_at": "2026-11-20T14:15:30Z"
  }
]
```

#### 2. `GET /api/v1/notifications/unread-count`
- **Description**: Lightweight endpoint for polling unread count.
- **Response `200 OK`**:
```json
{
  "unread_count": 3
}
```

#### 3. `PATCH /api/v1/notifications/{id}/read`
- **Description**: Mark an individual notification as read.
- **Response `200 OK`**:
```json
{
  "id": "e4b2d398-3bf2-45e8-b76f-8dc8c34f2d01",
  "is_read": true
}
```

#### 4. `POST /api/v1/notifications/read-all`
- **Description**: Mark all unread notifications for the user as read.
- **Response `200 OK`**:
```json
{
  "message": "All notifications marked as read.",
  "updated_count": 3
}
```

#### 5. `GET /api/v1/notifications/preferences` & `PATCH /api/v1/notifications/preferences`
- **Request Body (PATCH)**:
```json
{
  "notify_approvals": true,
  "notify_documents": true,
  "notify_security": true,
  "notify_analytics": true,
  "in_app_enabled": true,
  "email_enabled": false
}
```

---

### 5.2 Natural Language Data Analysis Endpoints

#### 1. `POST /api/v1/spreadsheets/nl-query`
- **Description**: Submit a natural language question against an uploaded spreadsheet.
- **Request Body**:
```json
{
  "document_id": "d04a6fc9-3e3e-4340-a29d-4ebba16eeec2",
  "sheet_name": "Sales_Q3",
  "question": "Which departments exceeded their allocated budgets?"
}
```
- **Response `200 OK`**:
```json
{
  "question": "Which departments exceeded their allocated budgets?",
  "operation": "budget_vs_actual",
  "answer": "1 department (Security) exceeded allocated budget by $30,000.00.",
  "explanation": "Financial variance analysis revealed that the Security department spent $280,000.00 against an allocated budget of $250,000.00, resulting in an unfavorable overrun of 12.0%. All other departments operated within allocated limits.",
  "data": {
    "columns": ["Department", "Budget", "Actual", "Variance", "Overrun"],
    "rows": [
      ["Infrastructure", 700000.0, 680000.0, -20000.0, false],
      ["Security", 250000.0, 280000.0, 30000.0, true]
    ],
    "row_count": 2,
    "overrun_count": 1
  },
  "chart_spec": {
    "type": "bar",
    "title": "Budget vs Actual Expenditure by Department",
    "x_axis": "Department",
    "y_axis": "Actual",
    "data": [
      {"label": "Infrastructure", "value": 680000.0},
      {"label": "Security", "value": 280000.0}
    ]
  },
  "execution_time_ms": 64.2
}
```
- **Error Codes**:
  - `401 Unauthorized`: Token missing or expired.
  - `403 Forbidden`: User's role lacks vault clearance to view this document.
  - `404 Not Found`: Document ID does not exist.
  - `422 Unprocessable Entity`: Question unsupported or target column not found in schema.

#### 2. `GET /api/v1/spreadsheets/{document_id}/schema`
- **Description**: Retrieve multi-tab schema profiles and intelligent suggested questions.
- **Query Parameters**: `sheet_name` (optional)
- **Response `200 OK`**:
```json
{
  "document_id": "d04a6fc9-3e3e-4340-a29d-4ebba16eeec2",
  "sheet_name": "Sales_Q3",
  "available_sheets": ["Sales_Q3", "Inventory_Status"],
  "row_count": 150,
  "columns": [
    {"name": "Department", "data_type": "string", "null_count": 0, "sample_values": ["Finance", "Engineering"]},
    {"name": "Expenditure", "data_type": "number", "null_count": 0, "sample_values": [45000.0, 12800.0]}
  ],
  "suggested_questions": [
    "Calculate the total Expenditure across all records",
    "Show the top 5 departments based on Expenditure",
    "Compare Expenditure across Department",
    "Detect outliers and abnormal values in Expenditure"
  ]
}
```

#### 3. `GET /api/v1/spreadsheets/nl-history`
- **Description**: Retrieve chronological analytical queries executed by the user.
- **Query Parameters**: `document_id` (optional), `limit` (default: 20)
- **Response `200 OK`**:
```json
[
  {
    "id": "a98c76b1-21fa-4390-bd91-0987165ef432",
    "document_id": "d04a6fc9-3e3e-4340-a29d-4ebba16eeec2",
    "question": "Show top 5 departments by expenditure",
    "operation": "ranking",
    "answer": "Top 5 records by Expenditure identified.",
    "created_at": "2026-11-20T14:10:00Z"
  }
]
```

---

## 6. Accessibility, Security & Production Best Practices

1. **Zero-Trust Security Grounding**: The front-end NEVER passes raw SQL or executable Python code to the backend. All natural language prompts are parsed server-side into structured analytical primitives against an explicit allowlist.
2. **Keyboard Accessibility**:
   - `Tab` navigation traverses the notification bell, unread items, question chips, and input bar in logical order.
   - `Enter` inside the prompt input triggers query analysis.
   - `Escape` closes the notification dropdown and modal sheets.
3. **Screen Reader Compliance (WCAG 2.1 AA)**:
   - Bell button includes `aria-label="Notifications"`.
   - Badge includes `aria-live="polite"` to notify assistive devices of new unread events.
   - Tables contain standard `<th>` headers with `scope="col"`.
4. **Resilient Offline / Degradation Modes**:
   - If Ollama is unavailable or booting, the deterministic calculation engine continues to output direct numerical answers and data tables immediately without blocking.

---

## 7. Verification & Implementation Checklist

- [x] Notification bell icon and dynamic badge mounted in header actions.
- [x] Notification dropdown renders category-coded event cards.
- [x] Background polling mechanism refreshes unread count every 15s.
- [x] Mark-as-read and mark-all-read update database and optimistic UI.
- [x] Preference modal allows granular control over alert categories and channels.
- [x] Spreadsheet studio includes Document & Sheet schema inspector.
- [x] Suggested question chips auto-populate based on detected columns.
- [x] Natural language query input supports free-form plain-English questions.
- [x] Direct answer card renders calculated numerical facts.
- [x] Executive AI narrative synthesizes context and managerial takeaways.
- [x] Pure vector SVG chart renders bar, line, and outlier specifications.
- [x] Query history enables 1-click re-execution of previous analyses.
- [x] 1-Click Export buttons download `.xlsx`, `.pdf`, and `.pptx` deliverables.
