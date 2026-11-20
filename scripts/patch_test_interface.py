"""Patch test-interface.html to add Enterprise Notifications & NL Analysis Workbench."""

from pathlib import Path

INTERFACE_PATH = Path("d:/projects/servergen-ai/test-interface.html")


def main():
    content = INTERFACE_PATH.read_text(encoding="utf-8")

    # 1. CSS
    css_addition = """
        /* Enterprise Notifications UI */
        .notif-wrapper {
            position: relative;
            display: inline-flex;
            align-items: center;
        }
        .notif-bell-btn {
            background: #ffffff;
            border: 1px solid var(--border-default);
            border-radius: 50%;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: var(--text-secondary);
            position: relative;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 0.95rem;
        }
        .notif-bell-btn:hover {
            background: #f1f5f9;
            color: var(--primary);
            border-color: var(--primary);
        }
        .notif-badge {
            position: absolute;
            top: -3px;
            right: -3px;
            background: #dc2626;
            color: #ffffff;
            border-radius: 10px;
            font-size: 0.65rem;
            font-weight: 700;
            padding: 1px 5px;
            min-width: 17px;
            text-align: center;
            border: 2px solid #ffffff;
            line-height: 1.2;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            animation: pulse-badge 2s infinite;
        }
        @keyframes pulse-badge {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.08); }
        }
        .notif-dropdown {
            position: absolute;
            top: calc(100% + 10px);
            right: 0;
            width: 390px;
            max-width: 92vw;
            background: #ffffff;
            border: 1px solid var(--border-default);
            border-radius: 12px;
            box-shadow: 0 14px 35px -5px rgba(0,0,0,0.12), 0 8px 12px -6px rgba(0,0,0,0.08);
            z-index: 1050;
            overflow: hidden;
            display: none;
            flex-direction: column;
        }
        .notif-dropdown-header {
            padding: 12px 16px;
            background: #f8fafc;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .notif-list {
            max-height: 380px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }
        .notif-item {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-subtle);
            cursor: pointer;
            transition: background 0.15s ease;
            display: flex;
            gap: 12px;
            align-items: flex-start;
            position: relative;
        }
        .notif-item:hover {
            background: #f8fafc;
        }
        .notif-item.unread {
            background: #f0f9ff;
        }
        .notif-item.unread::before {
            content: '';
            position: absolute;
            left: 5px;
            top: 18px;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #0284c7;
        }
        .notif-icon-box {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            font-size: 0.85rem;
        }
        .notif-icon-approval { background: #fef3c7; color: #d97706; }
        .notif-icon-document { background: #e0f2fe; color: #0284c7; }
        .notif-icon-security { background: #fee2e2; color: #dc2626; }
        .notif-icon-analytics { background: #dcfce7; color: #16a34a; }
        .notif-dropdown-footer {
            padding: 10px 16px;
            background: #f8fafc;
            border-top: 1px solid var(--border-subtle);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Natural Language Data Analysis Workbench Styles */
        .nl-workbench-container {
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            background: #ffffff;
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
            margin-top: 24px;
            padding: 24px;
        }
        .nl-chip-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
            border: 1px solid #cbd5e1;
            background: #f8fafc;
            color: #334155;
            user-select: none;
        }
        .nl-chip-btn:hover {
            background: #eff6ff;
            border-color: #38bdf8;
            color: #0284c7;
            transform: translateY(-1px);
            box-shadow: 0 2px 5px rgba(2, 132, 199, 0.12);
        }
        .nl-schema-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.74rem;
            background: #f1f5f9;
            border: 1px solid #e2e8f0;
            color: #334155;
        }
        .nl-badge-type {
            font-size: 0.65rem;
            text-transform: uppercase;
            padding: 1px 4px;
            border-radius: 3px;
            font-weight: 700;
        }
        .nl-type-number { background: #dbeafe; color: #1e40af; }
        .nl-type-string { background: #fef3c7; color: #92400e; }
        .nl-type-date { background: #e0e7ff; color: #3730a3; }
        .nl-result-answer {
            background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
            border-left: 5px solid #16a34a;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 18px;
        }
        .nl-result-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.82rem;
            margin-top: 10px;
        }
        .nl-result-table th {
            background: #f1f5f9;
            color: #475569;
            font-weight: 700;
            padding: 10px 14px;
            text-align: left;
            border-bottom: 2px solid #cbd5e1;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .nl-result-table td {
            padding: 9px 14px;
            border-bottom: 1px solid #e2e8f0;
            color: #1e293b;
        }
        .nl-result-table tr:hover td {
            background: #f8fafc;
        }
        .nl-history-item {
            padding: 10px 14px;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #ffffff;
            cursor: pointer;
            transition: all 0.15s ease;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .nl-history-item:hover {
            border-color: #0284c7;
            background: #f0f9ff;
        }
    </style>
"""

    if "/* Enterprise Notifications UI */" not in content:
        content = content.replace("    </style>", css_addition, 1)

    # 2. Header Actions
    header_bell = """
        <div class="header-actions">
            <!-- Enterprise Notification Bell & Dropdown -->
            <div class="notif-wrapper">
                <button id="notif-bell-btn" class="notif-bell-btn" onclick="toggleNotificationDropdown()" title="Notifications" aria-label="Notifications">
                    <i class="fa-solid fa-bell"></i>
                    <span id="notif-badge" class="notif-badge" style="display:none;">0</span>
                </button>
                <div id="notif-dropdown" class="notif-dropdown">
                    <div class="notif-dropdown-header">
                        <div style="font-weight:700; color:#0f172a; font-size:0.9rem; display:flex; align-items:center; gap:6px;">
                            <i class="fa-solid fa-bell text-primary"></i> Notifications
                            <span id="notif-header-count" class="badge badge-primary" style="font-size:0.7rem; padding:1px 6px;">0</span>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="markAllNotificationsRead()" style="font-size:0.72rem; padding:3px 8px;">
                            <i class="fa-solid fa-check-double"></i> Mark all read
                        </button>
                    </div>
                    <div id="notif-list" class="notif-list">
                        <div class="notif-empty" style="padding:24px; text-align:center; color:#94a3b8; font-size:0.8rem;">
                            <i class="fa-regular fa-bell-slash" style="font-size:1.8rem; margin-bottom:6px; display:block;"></i>
                            No new notifications
                        </div>
                    </div>
                    <div class="notif-dropdown-footer">
                        <span style="font-size:0.72rem; color:#64748b;">Enterprise Event Stream</span>
                        <button class="btn btn-sm" onclick="openNotificationPreferencesModal()" style="font-size:0.72rem; color:#0284c7; background:transparent; border:none; cursor:pointer;">
                            <i class="fa-solid fa-sliders"></i> Preferences
                        </button>
                    </div>
                </div>
            </div>
"""
    if "<!-- Enterprise Notification Bell & Dropdown -->" not in content:
        content = content.replace('<div class="header-actions">', header_bell, 1)

    # 3. Preferences Modal before </body>
    pref_modal = """
    <!-- Notification Preferences Modal -->
    <div id="notif-pref-modal" style="display:none; position:fixed; inset:0; background:rgba(15,23,42,0.5); z-index:1100; align-items:center; justify-content:center; padding:20px;">
        <div style="background:#ffffff; border-radius:12px; max-width:500px; width:100%; box-shadow:0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04); overflow:hidden;">
            <div style="padding:16px 20px; border-bottom:1px solid #e2e8f0; display:flex; justify-content:space-between; align-items:center; background:#f8fafc;">
                <h4 style="margin:0; font-size:1rem; color:#0f172a; display:flex; align-items:center; gap:8px;">
                    <i class="fa-solid fa-sliders text-primary"></i> Notification Preferences
                </h4>
                <button class="btn btn-secondary btn-sm" onclick="closeNotificationPreferencesModal()"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div style="padding:20px;">
                <p style="font-size:0.82rem; color:#64748b; margin-bottom:16px;">Configure real-time automated alerts and event notifications for your role.</p>
                <div style="display:flex; flex-direction:column; gap:12px;">
                    <label style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:#f8fafc; border-radius:6px; cursor:pointer;">
                        <span style="font-size:0.85rem; font-weight:600; color:#334155;"><i class="fa-solid fa-signature text-warning" style="width:20px;"></i> Approvals (Requests & Decisions)</span>
                        <input type="checkbox" id="pref-opt-approval" checked style="width:16px; height:16px; accent-color:#0284c7;">
                    </label>
                    <label style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:#f8fafc; border-radius:6px; cursor:pointer;">
                        <span style="font-size:0.85rem; font-weight:600; color:#334155;"><i class="fa-solid fa-file-circle-check text-primary" style="width:20px;"></i> Documents (Indexed & Role Vaults)</span>
                        <input type="checkbox" id="pref-opt-document" checked style="width:16px; height:16px; accent-color:#0284c7;">
                    </label>
                    <label style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:#f8fafc; border-radius:6px; cursor:pointer;">
                        <span style="font-size:0.85rem; font-weight:600; color:#334155;"><i class="fa-solid fa-shield-triangle-exclamation text-danger" style="width:20px;"></i> Security & Policy Alerts</span>
                        <input type="checkbox" id="pref-opt-security" checked style="width:16px; height:16px; accent-color:#0284c7;">
                    </label>
                    <label style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:#f8fafc; border-radius:6px; cursor:pointer;">
                        <span style="font-size:0.85rem; font-weight:600; color:#334155;"><i class="fa-solid fa-chart-line text-success" style="width:20px;"></i> Analytics & Spreadsheet Ready</span>
                        <input type="checkbox" id="pref-opt-analytics" checked style="width:16px; height:16px; accent-color:#0284c7;">
                    </label>
                </div>
                <div style="margin-top:16px; padding-top:14px; border-top:1px solid #e2e8f0; display:flex; gap:16px;">
                    <label style="display:inline-flex; align-items:center; gap:8px; font-size:0.8rem; color:#475569; cursor:pointer;">
                        <input type="checkbox" id="pref-channel-inapp" checked style="width:15px; height:15px; accent-color:#0284c7;"> In-App Bell
                    </label>
                    <label style="display:inline-flex; align-items:center; gap:8px; font-size:0.8rem; color:#475569; cursor:pointer;">
                        <input type="checkbox" id="pref-channel-email" checked style="width:15px; height:15px; accent-color:#0284c7;"> Email Digest
                    </label>
                </div>
            </div>
            <div style="padding:14px 20px; background:#f8fafc; border-top:1px solid #e2e8f0; display:flex; justify-content:flex-end; gap:10px;">
                <button class="btn btn-secondary btn-sm" onclick="closeNotificationPreferencesModal()">Cancel</button>
                <button class="btn btn-primary btn-sm" onclick="saveNotificationPreferences()"><i class="fa-solid fa-floppy-disk"></i> Save Preferences</button>
            </div>
        </div>
    </div>
</body>
"""
    if "<!-- Notification Preferences Modal -->" not in content:
        content = content.replace("</body>", pref_modal, 1)

    # 4. NL Workbench Markup inside panel-spreadsheets
    nl_workbench_html = """
                    <!-- FEATURE: NATURAL LANGUAGE DATA ANALYSIS WORKBENCH -->
                    <div class="nl-workbench-container" id="nl-workbench-card">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; flex-wrap:wrap; gap:10px;">
                            <div>
                                <div style="font-weight:800; font-size:1.15rem; color:#0f172a; display:flex; align-items:center; gap:10px;">
                                    <span style="background:linear-gradient(135deg, #0284c7 0%, #0369a1 100%); color:#fff; width:32px; height:32px; border-radius:8px; display:inline-flex; align-items:center; justify-content:center; font-size:0.95rem; box-shadow:0 2px 6px rgba(2,132,199,0.3);">
                                        <i class="fa-solid fa-comments"></i>
                                    </span>
                                    Natural Language Data Analysis Workbench
                                </div>
                                <div style="font-size:0.82rem; color:#64748b; margin-top:3px;">
                                    Ask plain-English questions about uploaded Excel or CSV data. Executed deterministically with Python data engines &amp; explained by AI.
                                </div>
                            </div>
                            <span class="badge badge-primary" style="font-size:0.75rem; padding:4px 10px;">
                                <i class="fa-solid fa-shield-check"></i> Safe Deterministic Execution
                            </span>
                        </div>

                        <!-- Document & Sheet Selector Bar -->
                        <div style="display:grid; grid-template-columns: 2fr 1fr auto; gap:12px; margin-bottom:16px; align-items:end;">
                            <div>
                                <label style="display:block; font-size:0.75rem; font-weight:700; color:#475569; margin-bottom:4px;">Active Spreadsheet File</label>
                                <select id="nl-doc-select" class="form-control" onchange="onNlDocumentChanged()" style="background:#fff; width:100%;">
                                    <option value="">-- Select Uploaded Spreadsheet --</option>
                                </select>
                            </div>
                            <div>
                                <label style="display:block; font-size:0.75rem; font-weight:700; color:#475569; margin-bottom:4px;">Worksheet</label>
                                <select id="nl-sheet-select" class="form-control" onchange="onNlSheetChanged()" style="background:#fff; width:100%;">
                                    <option value="">-- Active Sheet --</option>
                                </select>
                            </div>
                            <div>
                                <button type="button" class="btn btn-secondary" onclick="refreshNlDocuments()" title="Refresh uploaded documents list" style="height:38px;">
                                    <i class="fa-solid fa-rotate-right"></i>
                                </button>
                            </div>
                        </div>

                        <!-- Sheet Schema Profile Explorer -->
                        <div id="nl-schema-container" style="display:none; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px 16px; margin-bottom:16px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                <span style="font-size:0.75rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.04em;">
                                    <i class="fa-solid fa-table-columns text-primary"></i> Detected Columns &amp; Profiles (<span id="nl-schema-col-count">0</span> columns, <span id="nl-schema-row-count">0</span> rows)
                                </span>
                                <span id="nl-vault-badge" class="badge badge-info" style="font-size:0.7rem;">ROLE VAULT PROTECTED</span>
                            </div>
                            <div id="nl-schema-pills" style="display:flex; flex-wrap:wrap; gap:8px;">
                                <!-- Dynamically populated schema pills -->
                            </div>
                        </div>

                        <!-- Smart Suggested Questions Chips -->
                        <div id="nl-suggestions-section" style="margin-bottom:16px;">
                            <div style="font-size:0.75rem; font-weight:700; color:#475569; margin-bottom:6px; display:flex; align-items:center; gap:6px;">
                                <i class="fa-solid fa-lightbulb text-warning"></i> Recommended Analytical Questions:
                            </div>
                            <div id="nl-suggested-chips-container" style="display:flex; flex-wrap:wrap; gap:8px;">
                                <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('Calculate the total expenditure across all departments')"><i class="fa-solid fa-calculator text-primary"></i> Total Expenditure</button>
                                <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('Show the top 5 departments based on expenditure')"><i class="fa-solid fa-ranking-star text-warning"></i> Top 5 by Expenditure</button>
                                <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('Compare expenditure across departments')"><i class="fa-solid fa-layer-group text-info"></i> Compare by Department</button>
                                <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('Which departments exceeded their allocated budgets?')"><i class="fa-solid fa-scale-balanced text-danger"></i> Budget Overruns</button>
                                <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('Detect outliers and abnormal values in amount')"><i class="fa-solid fa-triangle-exclamation text-warning"></i> Outlier Detection</button>
                                <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('Find all duplicate records in this spreadsheet')"><i class="fa-solid fa-clone text-purple"></i> Find Duplicates</button>
                                <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('Show the monthly trend for expenditure')"><i class="fa-solid fa-chart-line text-success"></i> Monthly Trend</button>
                            </div>
                        </div>

                        <!-- Natural Language Query Input Bar -->
                        <div style="margin-bottom:16px;">
                            <div style="position:relative; display:flex; gap:10px;">
                                <input type="text" id="nl-query-input" class="form-control" placeholder="Ask in natural language: e.g. Which departments exceeded budget? or Show top 5 sales..." style="background:#fff; font-size:0.95rem; padding:12px 16px; border-radius:8px; border:1px solid #94a3b8; flex:1;" onkeydown="if(event.key==='Enter') executeNlQuery()">
                                <button id="nl-btn-submit" class="btn btn-primary" onclick="executeNlQuery()" style="padding:0 24px; font-weight:700; font-size:0.92rem; border-radius:8px; background:linear-gradient(135deg, #0284c7 0%, #0369a1 100%);">
                                    <i class="fa-solid fa-wand-magic-sparkles"></i> Ask AI
                                </button>
                            </div>
                        </div>

                        <!-- Status Alert / Loading indicator -->
                        <div id="nl-status-banner" style="display:none; padding:12px 16px; border-radius:8px; margin-bottom:16px; font-size:0.85rem;"></div>

                        <!-- Results Container -->
                        <div id="nl-results-view" style="display:none; margin-top:20px;">
                            <!-- Header with metadata & Export Deliverables -->
                            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid #e2e8f0;">
                                <div>
                                    <span id="nl-res-op-badge" class="badge badge-primary" style="text-transform:uppercase;">STATISTICAL</span>
                                    <span id="nl-res-time-badge" style="font-size:0.75rem; color:#64748b; margin-left:8px;">Execution: 0.05s</span>
                                    <span id="nl-res-count-badge" style="font-size:0.75rem; color:#64748b; margin-left:8px;">Rows: 0</span>
                                </div>
                                <div style="display:flex; gap:8px;">
                                    <button class="btn btn-secondary btn-sm" onclick="exportNlResultTo('xlsx')" style="font-size:0.76rem; padding:5px 12px;"><i class="fa-solid fa-file-excel text-success"></i> Export Excel</button>
                                    <button class="btn btn-secondary btn-sm" onclick="exportNlResultTo('pdf')" style="font-size:0.76rem; padding:5px 12px;"><i class="fa-solid fa-file-pdf text-danger"></i> Export PDF</button>
                                    <button class="btn btn-secondary btn-sm" onclick="exportNlResultTo('pptx')" style="font-size:0.76rem; padding:5px 12px;"><i class="fa-solid fa-file-powerpoint text-warning"></i> Export Slide Deck</button>
                                </div>
                            </div>

                            <!-- Direct Answer Callout -->
                            <div class="nl-result-answer">
                                <div style="font-size:0.75rem; font-weight:700; color:#15803d; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:4px;">
                                    <i class="fa-solid fa-circle-check"></i> Direct Answer
                                </div>
                                <div id="nl-direct-answer-text" style="font-size:1.1rem; font-weight:700; color:#0f172a; line-height:1.4;">
                                    --
                                </div>
                            </div>

                            <!-- Executive AI Explanation Narrative -->
                            <div id="nl-explanation-container" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px 20px; margin-bottom:18px;">
                                <div style="font-size:0.75rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px; display:flex; align-items:center; gap:6px;">
                                    <i class="fa-solid fa-brain text-primary"></i> Executive AI Analysis &amp; Interpretation
                                </div>
                                <div id="nl-explanation-text" style="font-size:0.86rem; color:#334155; line-height:1.6; white-space:pre-line;">
                                    --
                                </div>
                            </div>

                            <!-- Visual Chart Container -->
                            <div id="nl-chart-wrapper" style="display:none; background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:18px; margin-bottom:18px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                                    <span id="nl-chart-title" style="font-weight:700; font-size:0.88rem; color:#0f172a;"><i class="fa-solid fa-chart-column text-primary"></i> Visualization</span>
                                    <span id="nl-chart-type-tag" class="badge badge-secondary" style="font-size:0.7rem; text-transform:uppercase;">BAR CHART</span>
                                </div>
                                <div id="nl-chart-render" style="width:100%; min-height:220px; display:flex; align-items:center; justify-content:center;">
                                    <!-- Rendered SVG Chart -->
                                </div>
                            </div>

                            <!-- Tabular Data View -->
                            <div id="nl-table-wrapper" style="display:none; background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:16px; margin-bottom:18px; overflow-x:auto;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                                    <span style="font-weight:700; font-size:0.85rem; color:#0f172a;"><i class="fa-solid fa-table text-primary"></i> Structured Data Results</span>
                                    <span id="nl-table-meta" style="font-size:0.75rem; color:#64748b;">0 records</span>
                                </div>
                                <div id="nl-table-render" style="max-height:350px; overflow-y:auto;">
                                    <!-- Dynamic table -->
                                </div>
                            </div>
                        </div>

                        <!-- Query History Drawer / List -->
                        <div style="margin-top:20px; border-top:1px solid #e2e8f0; padding-top:16px;">
                            <details id="nl-history-details">
                                <summary style="font-size:0.82rem; font-weight:700; color:#475569; cursor:pointer; user-select:none; display:flex; align-items:center; gap:6px;">
                                    <i class="fa-solid fa-clock-rotate-left text-primary"></i> Analysis History &amp; Previous Questions (<span id="nl-history-count">0</span>)
                                </summary>
                                <div id="nl-history-list" style="margin-top:12px;">
                                    <div style="font-size:0.78rem; color:#94a3b8; text-align:center; padding:12px;">No previous queries for this document.</div>
                                </div>
                            </details>
                        </div>
                    </div>
                </div>
            </div>

            <!-- TAB: 5 CORE SYSTEM VERIFICATION TESTS -->
"""
    anchor_nl = """                </div>
            </div>

            <!-- TAB: 5 CORE SYSTEM VERIFICATION TESTS -->"""

    if "<!-- FEATURE: NATURAL LANGUAGE DATA ANALYSIS WORKBENCH -->" not in content:
        content = content.replace(anchor_nl, nl_workbench_html, 1)

    # 5. JavaScript functions
    js_code = """
        // =========================================================================
        // AUTOMATED NOTIFICATIONS CLIENT LOGIC
        // =========================================================================
        let notifState = {
            unreadCount: 0,
            notifications: [],
            pollTimer: null
        };

        function toggleNotificationDropdown() {
            const dropdown = document.getElementById('notif-dropdown');
            if (!dropdown) return;
            const isOpen = dropdown.style.display === 'flex';
            dropdown.style.display = isOpen ? 'none' : 'flex';
            if (!isOpen) {
                fetchNotifications(true);
            }
        }

        function closeNotificationDropdown() {
            const dropdown = document.getElementById('notif-dropdown');
            if (dropdown) dropdown.style.display = 'none';
        }

        document.addEventListener('click', (e) => {
            const wrapper = document.querySelector('.notif-wrapper');
            const dropdown = document.getElementById('notif-dropdown');
            if (wrapper && dropdown && !wrapper.contains(e.target) && dropdown.style.display === 'flex') {
                dropdown.style.display = 'none';
            }
        });

        async function fetchNotifications(updateList = false) {
            if (!state.token) return;
            try {
                // Fetch unread count
                const countRes = await api('GET', '/api/v1/notifications/unread-count');
                if (countRes.ok && countRes.data) {
                    notifState.unreadCount = countRes.data.unread_count || 0;
                    const badge = document.getElementById('notif-badge');
                    const headerCount = document.getElementById('notif-header-count');
                    if (badge) {
                        badge.textContent = notifState.unreadCount;
                        badge.style.display = notifState.unreadCount > 0 ? 'inline-block' : 'none';
                    }
                    if (headerCount) {
                        headerCount.textContent = notifState.unreadCount;
                    }
                }

                // If dropdown is open or requested, load list
                if (updateList || document.getElementById('notif-dropdown')?.style.display === 'flex') {
                    const listRes = await api('GET', '/api/v1/notifications?limit=25');
                    if (listRes.ok && Array.isArray(listRes.data)) {
                        notifState.notifications = listRes.data;
                        renderNotificationList();
                    }
                }
            } catch (err) {
                console.error('Error fetching notifications:', err);
            }
        }

        function renderNotificationList() {
            const listEl = document.getElementById('notif-list');
            if (!listEl) return;
            if (notifState.notifications.length === 0) {
                listEl.innerHTML = `
                    <div style="padding:28px 16px; text-align:center; color:#94a3b8; font-size:0.8rem;">
                        <i class="fa-regular fa-bell-slash" style="font-size:1.8rem; margin-bottom:8px; display:block; color:#cbd5e1;"></i>
                        No notifications found for this account.
                    </div>`;
                return;
            }

            let html = '';
            notifState.notifications.forEach(n => {
                const isUnread = !n.is_read;
                let iconClass = 'fa-solid fa-bell';
                let iconBoxClass = 'notif-icon-approval';
                if (n.category === 'approval') {
                    iconClass = 'fa-solid fa-signature';
                    iconBoxClass = 'notif-icon-approval';
                } else if (n.category === 'document') {
                    iconClass = 'fa-solid fa-file-circle-check';
                    iconBoxClass = 'notif-icon-document';
                } else if (n.category === 'security') {
                    iconClass = 'fa-solid fa-shield-triangle-exclamation';
                    iconBoxClass = 'notif-icon-security';
                } else if (n.category === 'analytics') {
                    iconClass = 'fa-solid fa-chart-line';
                    iconBoxClass = 'notif-icon-analytics';
                }

                const timeStr = n.created_at ? new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

                html += `
                    <div class="notif-item ${isUnread ? 'unread' : ''}" onclick="markNotificationRead('${escapeHtml(n.id)}')">
                        <div class="notif-icon-box ${iconBoxClass}">
                            <i class="${iconClass}"></i>
                        </div>
                        <div style="flex:1; min-width:0;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
                                <span style="font-weight:700; font-size:0.82rem; color:#0f172a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                    ${escapeHtml(n.title)}
                                </span>
                                <span style="font-size:0.68rem; color:#94a3b8; margin-left:6px; flex-shrink:0;">${timeStr}</span>
                            </div>
                            <div style="font-size:0.75rem; color:#475569; line-height:1.4;">
                                ${escapeHtml(n.message)}
                            </div>
                        </div>
                    </div>
                `;
            });
            listEl.innerHTML = html;
        }

        async function markNotificationRead(notifId) {
            try {
                await api('PATCH', `/api/v1/notifications/${notifId}/read`);
                const item = notifState.notifications.find(n => n.id === notifId);
                if (item) item.is_read = true;
                if (notifState.unreadCount > 0) notifState.unreadCount--;
                const badge = document.getElementById('notif-badge');
                if (badge) {
                    badge.textContent = notifState.unreadCount;
                    badge.style.display = notifState.unreadCount > 0 ? 'inline-block' : 'none';
                }
                renderNotificationList();
            } catch (err) {
                console.error('Error marking notification read:', err);
            }
        }

        async function markAllNotificationsRead() {
            try {
                await api('POST', '/api/v1/notifications/read-all');
                notifState.notifications.forEach(n => n.is_read = true);
                notifState.unreadCount = 0;
                const badge = document.getElementById('notif-badge');
                if (badge) {
                    badge.textContent = '0';
                    badge.style.display = 'none';
                }
                renderNotificationList();
                showToast('All notifications marked as read', 'success');
            } catch (err) {
                console.error('Error marking all notifications read:', err);
            }
        }

        function openNotificationPreferencesModal() {
            closeNotificationDropdown();
            document.getElementById('notif-pref-modal').style.display = 'flex';
            loadNotificationPreferences();
        }

        function closeNotificationPreferencesModal() {
            document.getElementById('notif-pref-modal').style.display = 'none';
        }

        async function loadNotificationPreferences() {
            try {
                const res = await api('GET', '/api/v1/notifications/preferences');
                if (res.ok && res.data) {
                    const p = res.data;
                    document.getElementById('pref-opt-approval').checked = p.notify_approvals ?? true;
                    document.getElementById('pref-opt-document').checked = p.notify_documents ?? true;
                    document.getElementById('pref-opt-security').checked = p.notify_security ?? true;
                    document.getElementById('pref-opt-analytics').checked = p.notify_analytics ?? true;
                    document.getElementById('pref-channel-inapp').checked = p.in_app_enabled ?? true;
                    document.getElementById('pref-channel-email').checked = p.email_enabled ?? false;
                }
            } catch (err) {
                console.error('Error loading preferences:', err);
            }
        }

        async function saveNotificationPreferences() {
            const body = {
                notify_approvals: document.getElementById('pref-opt-approval').checked,
                notify_documents: document.getElementById('pref-opt-document').checked,
                notify_security: document.getElementById('pref-opt-security').checked,
                notify_analytics: document.getElementById('pref-opt-analytics').checked,
                in_app_enabled: document.getElementById('pref-channel-inapp').checked,
                email_enabled: document.getElementById('pref-channel-email').checked
            };
            try {
                const res = await api('PATCH', '/api/v1/notifications/preferences', body);
                if (res.ok) {
                    closeNotificationPreferencesModal();
                    showToast('Notification preferences saved', 'success');
                } else {
                    alert(res.data?.detail || 'Failed to save preferences');
                }
            } catch (err) {
                alert('Error saving preferences: ' + err.message);
            }
        }

        // =========================================================================
        // NATURAL LANGUAGE DATA ANALYSIS WORKBENCH CLIENT LOGIC
        // =========================================================================
        let nlState = {
            activeDocId: null,
            activeSheetName: null,
            schema: null,
            lastResult: null,
            allDocs: []
        };

        async function refreshNlDocuments() {
            try {
                const res = await api('GET', '/api/v1/rag/documents');
                const docSelect = document.getElementById('nl-doc-select');
                if (!docSelect) return;

                docSelect.innerHTML = '<option value="">-- Select Uploaded Spreadsheet --</option>';

                if (res.ok && Array.isArray(res.data)) {
                    // Filter spreadsheets (.xlsx, .xls, .csv)
                    const sheets = res.data.filter(d => {
                        const t = (d.title || d.filename || '').toLowerCase();
                        return t.endsWith('.xlsx') || t.endsWith('.xls') || t.endsWith('.csv');
                    });
                    nlState.allDocs = sheets;
                    sheets.forEach(d => {
                        const opt = document.createElement('option');
                        opt.value = d.id;
                        opt.textContent = `${d.title || d.filename} (${d.classification || 'INTERNAL'})`;
                        docSelect.appendChild(opt);
                    });

                    // If active spreadsheet was already loaded, auto-select it
                    if (sheetState.docId && sheets.some(d => d.id === sheetState.docId)) {
                        docSelect.value = sheetState.docId;
                        onNlDocumentChanged();
                    } else if (sheets.length > 0 && !docSelect.value) {
                        docSelect.value = sheets[0].id;
                        onNlDocumentChanged();
                    }
                }
            } catch (err) {
                console.error('Error refreshing NL documents:', err);
            }
        }

        async function onNlDocumentChanged() {
            const docId = document.getElementById('nl-doc-select').value;
            nlState.activeDocId = docId;
            if (!docId) {
                document.getElementById('nl-schema-container').style.display = 'none';
                return;
            }

            // Sync with sheetState
            sheetState.docId = docId;

            // Fetch schema
            try {
                const res = await api('GET', `/api/v1/spreadsheets/${docId}/schema`);
                if (res.ok && res.data) {
                    renderNlSchema(res.data);
                    loadNlHistory(docId);
                } else {
                    document.getElementById('nl-schema-container').style.display = 'none';
                    if (res.status === 403) {
                        showToast('Document is in a restricted role vault (Access Denied).', 'danger');
                    }
                }
            } catch (err) {
                console.error('Error fetching schema:', err);
            }
        }

        function onNlSheetChanged() {
            const sheetSelect = document.getElementById('nl-sheet-select');
            nlState.activeSheetName = sheetSelect.value;
            if (nlState.activeDocId) {
                api('GET', `/api/v1/spreadsheets/${nlState.activeDocId}/schema?sheet_name=${encodeURIComponent(nlState.activeSheetName)}`).then(res => {
                    if (res.ok && res.data) renderNlSchema(res.data);
                });
            }
        }

        function renderNlSchema(data) {
            nlState.schema = data;
            const container = document.getElementById('nl-schema-container');
            const pillsBox = document.getElementById('nl-schema-pills');
            const sheetSelect = document.getElementById('nl-sheet-select');
            const colCount = document.getElementById('nl-schema-col-count');
            const rowCount = document.getElementById('nl-schema-row-count');

            if (!container || !pillsBox) return;

            container.style.display = 'block';
            colCount.textContent = data.columns?.length || 0;
            rowCount.textContent = data.row_count || 0;

            // Populate sheet selector if sheets are listed
            if (data.available_sheets && data.available_sheets.length > 0) {
                sheetSelect.innerHTML = '';
                data.available_sheets.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s;
                    opt.textContent = s;
                    if (s === data.sheet_name) opt.selected = true;
                    sheetSelect.appendChild(opt);
                });
            }

            // Render column schema pills
            let pillsHtml = '';
            (data.columns || []).forEach(c => {
                let typeClass = 'nl-type-string';
                if (c.data_type === 'number') typeClass = 'nl-type-number';
                else if (c.data_type === 'date') typeClass = 'nl-type-date';

                pillsHtml += `
                    <div class="nl-schema-pill">
                        <span style="font-weight:700;">${escapeHtml(c.name)}</span>
                        <span class="nl-badge-type ${typeClass}">${escapeHtml(c.data_type)}</span>
                        ${c.null_count > 0 ? `<span style="color:#ef4444; font-size:0.65rem;">${c.null_count} nulls</span>` : ''}
                    </div>
                `;
            });
            pillsBox.innerHTML = pillsHtml;

            // Render dynamic suggested questions if provided
            if (data.suggested_questions && data.suggested_questions.length > 0) {
                const chipsBox = document.getElementById('nl-suggested-chips-container');
                if (chipsBox) {
                    let chipsHtml = '';
                    data.suggested_questions.forEach(q => {
                        chipsHtml += `
                            <button type="button" class="nl-chip-btn" onclick="applyNlQuestion('${escapeHtml(q)}')">
                                <i class="fa-solid fa-wand-magic-sparkles text-primary"></i> ${escapeHtml(q)}
                            </button>
                        `;
                    });
                    chipsBox.innerHTML = chipsHtml;
                }
            }
        }

        function applyNlQuestion(q) {
            const inp = document.getElementById('nl-query-input');
            if (inp) {
                inp.value = q;
                inp.focus();
                executeNlQuery();
            }
        }

        async function executeNlQuery() {
            const docId = document.getElementById('nl-doc-select')?.value;
            const query = (document.getElementById('nl-query-input')?.value || '').trim();
            const sheetSelect = document.getElementById('nl-sheet-select');
            const sheetName = sheetSelect ? sheetSelect.value : null;

            if (!docId) {
                alert('Please select or upload a spreadsheet file first.');
                return;
            }
            if (!query) {
                alert('Please enter a question in plain English.');
                return;
            }

            const btn = document.getElementById('nl-btn-submit');
            const statusBanner = document.getElementById('nl-status-banner');
            const resultsView = document.getElementById('nl-results-view');

            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...';
            statusBanner.style.display = 'block';
            statusBanner.style.background = '#eff6ff';
            statusBanner.style.border = '1px solid #bfdbfe';
            statusBanner.style.color = '#1e40af';
            statusBanner.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Parsing intent, running deterministic Python calculations & synthesizing explanation...';

            try {
                const res = await api('POST', '/api/v1/spreadsheets/nl-query', {
                    document_id: docId,
                    question: query,
                    sheet_name: sheetName || undefined
                });

                if (!res.ok) {
                    throw new Error(res.data?.detail || 'Analysis request failed.');
                }

                statusBanner.style.display = 'none';
                nlState.lastResult = res.data;
                renderNlResult(res.data);
                loadNlHistory(docId);
                fetchNotifications(); // Refresh notifications in case analytics alert fired
            } catch (err) {
                statusBanner.style.display = 'block';
                statusBanner.style.background = '#fef2f2';
                statusBanner.style.border = '1px solid #fecaca';
                statusBanner.style.color = '#991b1b';
                statusBanner.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> Error: ${escapeHtml(err.message)}`;
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Ask AI';
            }
        }

        function renderNlResult(data) {
            const resultsView = document.getElementById('nl-results-view');
            if (!resultsView) return;
            resultsView.style.display = 'block';

            // Badges & Meta
            document.getElementById('nl-res-op-badge').textContent = (data.operation || 'analysis').toUpperCase();
            document.getElementById('nl-res-time-badge').textContent = `Execution: ${(data.execution_time_ms / 1000).toFixed(2)}s`;
            document.getElementById('nl-res-count-badge').textContent = `Rows: ${data.data?.row_count ?? (data.data?.rows?.length || 0)}`;

            // Direct Answer
            document.getElementById('nl-direct-answer-text').textContent = data.answer || 'Analysis complete.';

            // Executive Explanation Narrative
            const expEl = document.getElementById('nl-explanation-text');
            expEl.textContent = data.explanation || 'No narrative explanation generated.';

            // Chart Rendering
            const chartWrapper = document.getElementById('nl-chart-wrapper');
            const chartRender = document.getElementById('nl-chart-render');
            if (data.chart_spec && data.chart_spec.data && data.chart_spec.data.length > 0) {
                chartWrapper.style.display = 'block';
                document.getElementById('nl-chart-title').innerHTML = `<i class="fa-solid fa-chart-column text-primary"></i> ${escapeHtml(data.chart_spec.title || 'Visualization')}`;
                document.getElementById('nl-chart-type-tag').textContent = (data.chart_spec.type || 'chart').toUpperCase();
                renderSvgChart(chartRender, data.chart_spec);
            } else {
                chartWrapper.style.display = 'none';
            }

            // Tabular Data
            const tableWrapper = document.getElementById('nl-table-wrapper');
            const tableRender = document.getElementById('nl-table-render');
            const tableMeta = document.getElementById('nl-table-meta');
            const columns = data.data?.columns || [];
            const rows = data.data?.rows || [];

            if (columns.length > 0 && rows.length > 0) {
                tableWrapper.style.display = 'block';
                tableMeta.textContent = `${rows.length} records shown`;

                let tableHtml = '<table class="nl-result-table"><thead><tr>';
                columns.forEach(col => {
                    tableHtml += `<th>${escapeHtml(col)}</th>`;
                });
                tableHtml += '</tr></thead><tbody>';

                rows.slice(0, 100).forEach(r => {
                    tableHtml += '<tr>';
                    r.forEach(val => {
                        let formatted = val === null || val === undefined ? '<span style="color:#94a3b8;">null</span>' : escapeHtml(String(val));
                        tableHtml += `<td>${formatted}</td>`;
                    });
                    tableHtml += '</tr>';
                });
                tableHtml += '</tbody></table>';
                if (rows.length > 100) {
                    tableHtml += `<div style="font-size:0.75rem; color:#64748b; padding:8px; text-align:center;">Showing first 100 of ${rows.length} rows.</div>`;
                }
                tableRender.innerHTML = tableHtml;
            } else {
                tableWrapper.style.display = 'none';
            }
        }

        function renderSvgChart(container, spec) {
            const chartData = spec.data || [];
            const chartType = spec.type || 'bar';
            const width = 640;
            const height = 240;
            const padding = { top: 25, right: 30, bottom: 50, left: 70 };

            if (chartData.length === 0) {
                container.innerHTML = '<div style="color:#94a3b8;">No data for chart</div>';
                return;
            }

            const values = chartData.map(d => Number(d.value) || 0);
            const maxVal = Math.max(...values, 1);
            const minVal = Math.min(...values, 0);
            const valRange = maxVal - (minVal < 0 ? minVal : 0);

            let svg = `<svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; max-height:280px; font-family:var(--font-sans);" xmlns="http://www.w3.org/2000/svg">`;

            // Draw grid lines
            const gridCount = 4;
            for (let i = 0; i <= gridCount; i++) {
                const y = padding.top + (height - padding.top - padding.bottom) * (i / gridCount);
                const val = maxVal - (valRange * (i / gridCount));
                svg += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#e2e8f0" stroke-dasharray="3,3" />`;
                svg += `<text x="${padding.left - 8}" y="${y + 4}" fill="#64748b" font-size="10" text-anchor="end">${val.toLocaleString(undefined, { maximumFractionDigits: 1 })}</text>`;
            }

            const plotW = width - padding.left - padding.right;
            const plotH = height - padding.top - padding.bottom;

            if (chartType === 'line') {
                // Line chart
                let points = [];
                const step = plotW / Math.max(chartData.length - 1, 1);
                chartData.forEach((d, i) => {
                    const x = padding.left + i * step;
                    const y = padding.top + plotH - ((d.value - (minVal < 0 ? minVal : 0)) / valRange) * plotH;
                    points.push(`${x},${y}`);
                });

                svg += `<polyline fill="none" stroke="#0284c7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${points.join(' ')}" />`;

                chartData.forEach((d, i) => {
                    const x = padding.left + i * step;
                    const y = padding.top + plotH - ((d.value - (minVal < 0 ? minVal : 0)) / valRange) * plotH;
                    svg += `<circle cx="${x}" cy="${y}" r="4" fill="#ffffff" stroke="#0284c7" stroke-width="2.5" />`;
                    const label = String(d.label || '').substring(0, 10);
                    svg += `<text x="${x}" y="${height - padding.bottom + 16}" fill="#475569" font-size="10" text-anchor="middle">${escapeHtml(label)}</text>`;
                });
            } else {
                // Bar chart
                const barSpacing = plotW / chartData.length;
                const barWidth = Math.min(barSpacing * 0.65, 45);

                chartData.forEach((d, i) => {
                    const x = padding.left + i * barSpacing + (barSpacing - barWidth) / 2;
                    const barH = ((d.value - (minVal < 0 ? minVal : 0)) / valRange) * plotH;
                    const y = padding.top + plotH - barH;
                    const color = i % 2 === 0 ? '#0284c7' : '#38bdf8';

                    svg += `<rect x="${x}" y="${y}" width="${barWidth}" height="${Math.max(barH, 2)}" rx="4" fill="${color}" opacity="0.9" />`;
                    const label = String(d.label || '').substring(0, 10);
                    svg += `<text x="${x + barWidth / 2}" y="${height - padding.bottom + 16}" fill="#475569" font-size="10" text-anchor="middle">${escapeHtml(label)}</text>`;
                });
            }

            svg += '</svg>';
            container.innerHTML = svg;
        }

        async function loadNlHistory(docId) {
            try {
                const res = await api('GET', `/api/v1/spreadsheets/nl-history?document_id=${docId}&limit=10`);
                const listEl = document.getElementById('nl-history-list');
                const countEl = document.getElementById('nl-history-count');
                if (!listEl) return;

                if (res.ok && Array.isArray(res.data) && res.data.length > 0) {
                    countEl.textContent = res.data.length;
                    let html = '';
                    res.data.forEach(h => {
                        const timeStr = h.created_at ? new Date(h.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
                        html += `
                            <div class="nl-history-item" onclick="applyNlQuestion('${escapeHtml(h.question)}')">
                                <div style="flex:1;">
                                    <div style="font-weight:600; font-size:0.82rem; color:#0f172a;">${escapeHtml(h.question)}</div>
                                    <div style="font-size:0.72rem; color:#64748b;">${escapeHtml(h.operation.toUpperCase())} &bull; ${escapeHtml(h.answer ? h.answer.substring(0, 80) : '')}...</div>
                                </div>
                                <span style="font-size:0.7rem; color:#94a3b8; margin-left:10px;">${timeStr}</span>
                            </div>
                        `;
                    });
                    listEl.innerHTML = html;
                } else {
                    countEl.textContent = '0';
                    listEl.innerHTML = '<div style="font-size:0.78rem; color:#94a3b8; text-align:center; padding:12px;">No previous queries for this document.</div>';
                }
            } catch (err) {
                console.error('Error loading NL history:', err);
            }
        }

        async function exportNlResultTo(format) {
            if (!nlState.activeDocId || !nlState.lastResult) {
                alert('Run an analysis first before exporting results.');
                return;
            }
            try {
                const res = await api('POST', '/api/v1/spreadsheets/export', {
                    document_id: nlState.activeDocId,
                    sheet_name: nlState.activeSheetName || 'Sheet1',
                    export_format: format,
                    report_title: `Analysis - ${nlState.lastResult.question || 'Report'}`
                });
                if (res.ok && res.data && res.data.download_url) {
                    window.location.href = res.data.download_url;
                } else {
                    alert('Export completed. Check server outputs.');
                }
            } catch (err) {
                alert('Export failed: ' + err.message);
            }
        }
"""

    if "// AUTOMATED NOTIFICATIONS CLIENT LOGIC" not in content:
        content = content.replace("async function init() {", js_code + "\n        async function init() {", 1)

    # 6. Hook fetchNotifications in init() and quickSwitchRole()
    if "fetchNotifications();" not in content:
        content = content.replace(
            "checkSystemHealth();",
            "checkSystemHealth();\n            fetchNotifications();\n            setInterval(fetchNotifications, 15000);",
            1
        )

    if "refreshNlDocuments();" not in content:
        content = content.replace(
            "renderPresets();\n            await fetchMyProfile();",
            "renderPresets();\n            await fetchMyProfile();\n            fetchNotifications();\n            refreshNlDocuments();",
            1
        )

    INTERFACE_PATH.write_text(content, encoding="utf-8")
    print("SUCCESS: test-interface.html successfully patched!")


if __name__ == "__main__":
    main()
