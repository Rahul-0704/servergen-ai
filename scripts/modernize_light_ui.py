"""
ServerGen AI — Modernize Dashboard to Clean Light Enterprise UI.

Converts dark color scheme into a high-contrast, professional, readable
enterprise light theme (slate/white/blue) and adds clear project workflow
guidance to the dashboard.
"""

import re

with open('test-interface.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update :root
old_root = """        :root {
            --bg-base: #0a0f1d;
            --bg-surface: #111827;
            --bg-card: #162032;
            --bg-elevated: #1e293b;
            --bg-input: #0f172a;
            --border-subtle: #1e293b;
            --border-default: #334155;
            --border-focus: #38bdf8;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --primary: #0284c7;
            --primary-hover: #0369a1;
            --primary-glow: rgba(56, 189, 248, 0.25);
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --purple: #8b5cf6;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }"""

new_root = """        :root {
            --bg-base: #f8fafc;
            --bg-surface: #ffffff;
            --bg-card: #ffffff;
            --bg-elevated: #f1f5f9;
            --bg-input: #ffffff;
            --border-subtle: #e2e8f0;
            --border-default: #cbd5e1;
            --border-focus: #0284c7;
            --text-primary: #0f172a;
            --text-secondary: #334155;
            --text-muted: #64748b;
            --primary: #0284c7;
            --primary-hover: #0369a1;
            --primary-glow: rgba(2, 132, 199, 0.15);
            --success: #059669;
            --warning: #d97706;
            --danger: #dc2626;
            --purple: #7c3aed;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }"""

if old_root in html:
    html = html.replace(old_root, new_root)

# 2. Modernize Header & Brand styles
html = re.sub(
    r'header\s*\{[^}]*background:[^}]*\}',
    '''header {
            background: #ffffff;
            border-bottom: 1px solid var(--border-subtle);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 50;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }''',
    html
)

# Brand title in header
html = html.replace(
    '.brand-title {\n            font-size: 1.1rem;\n            font-weight: 700;\n            letter-spacing: -0.02em;\n            color: #fff;\n        }',
    '.brand-title {\n            font-size: 1.1rem;\n            font-weight: 700;\n            letter-spacing: -0.02em;\n            color: #0f172a;\n        }'
)

html = html.replace(
    '.brand-tag {\n            background: rgba(56, 189, 248, 0.12);\n            color: #38bdf8;',
    '.brand-tag {\n            background: #eff6ff;\n            color: #0284c7;'
)

# 3. Telemetry bar
html = html.replace(
    '/* System Telemetry Bar */\n        .telemetry-bar {\n            background: #0d1322;',
    '/* System Telemetry Bar */\n        .telemetry-bar {\n            background: #ffffff;'
)

# 4. Nav items & aside
html = html.replace(
    'aside {\n            width: 240px;\n            background: var(--bg-surface);',
    'aside {\n            width: 240px;\n            background: #ffffff;'
)

html = html.replace(
    '.nav-item.active {\n            color: #38bdf8;\n            background: rgba(56, 189, 248, 0.1);\n            border-color: rgba(56, 189, 248, 0.25);',
    '.nav-item.active {\n            color: #0284c7;\n            background: #eff6ff;\n            border-color: #bfdbfe;'
)

# 5. Cards & Titles
html = html.replace(
    '.card {\n            background: var(--bg-card);\n            border: 1px solid var(--border-subtle);\n            border-radius: 10px;\n            padding: 20px;\n            margin-bottom: 20px;\n            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);\n        }',
    '.card {\n            background: #ffffff;\n            border: 1px solid var(--border-subtle);\n            border-radius: 10px;\n            padding: 20px 24px;\n            margin-bottom: 20px;\n            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.03);\n        }'
)

html = html.replace(
    '.card-title {\n            font-size: 1rem;\n            font-weight: 600;\n            color: #fff;',
    '.card-title {\n            font-size: 1.05rem;\n            font-weight: 700;\n            color: #0f172a;'
)

# 6. Inputs & Selects
html = html.replace(
    'input, select, textarea {\n            width: 100%;\n            background: var(--bg-input);\n            border: 1px solid var(--border-default);\n            border-radius: 6px;\n            color: #fff;',
    'input, select, textarea {\n            width: 100%;\n            background: #ffffff;\n            border: 1px solid var(--border-default);\n            border-radius: 6px;\n            color: #0f172a;'
)

html = html.replace(
    'label {\n            font-size: 0.78rem;\n            font-weight: 500;\n            color: var(--text-secondary);\n        }',
    'label {\n            font-size: 0.78rem;\n            font-weight: 600;\n            color: #334155;\n        }'
)

# 7. Tables
html = html.replace(
    'th {\n            background: #111a2e;\n            padding: 10px 12px;\n            color: var(--text-secondary);\n            font-weight: 600;\n            border-bottom: 1px solid var(--border-subtle);\n        }',
    'th {\n            background: #f8fafc;\n            padding: 10px 14px;\n            color: #475569;\n            font-weight: 600;\n            border-bottom: 1px solid var(--border-subtle);\n        }'
)

html = html.replace(
    'td {\n            padding: 10px 12px;\n            border-bottom: 1px solid var(--border-subtle);\n            color: #cbd5e1;\n        }',
    'td {\n            padding: 10px 14px;\n            border-bottom: 1px solid #f1f5f9;\n            color: #0f172a;\n        }'
)

html = html.replace(
    'tr:hover td { background: rgba(255, 255, 255, 0.02); }',
    'tr:hover td { background: #f8fafc; }'
)

# 8. Quick Role Switcher
html = html.replace(
    '.role-switcher-container {\n            display: flex;\n            align-items: center;\n            gap: 8px;\n            background: rgba(15, 23, 42, 0.7);',
    '.role-switcher-container {\n            display: flex;\n            align-items: center;\n            gap: 8px;\n            background: #f1f5f9;'
)

html = html.replace(
    '.role-pill-btn.active {\n            background: rgba(56, 189, 248, 0.15);\n            border-color: rgba(56, 189, 248, 0.4);\n            color: #38bdf8;\n            box-shadow: 0 0 10px rgba(56, 189, 248, 0.2);\n        }',
    '.role-pill-btn.active {\n            background: #ffffff;\n            border-color: #cbd5e1;\n            color: #0284c7;\n            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);\n        }'
)

# 9. Scenarios Container & Cards
html = html.replace(
    '.scenarios-container {\n            background: rgba(15, 23, 42, 0.6);',
    '.scenarios-container {\n            background: #f8fafc;'
)

html = html.replace(
    '.scenario-card {\n            background: var(--bg-card);\n            border: 1px solid var(--border-subtle);',
    '.scenario-card {\n            background: #ffffff;\n            border: 1px solid var(--border-subtle);'
)

html = html.replace(
    '.scenario-card:hover {\n            border-color: #38bdf8;\n            transform: translateY(-2px);\n            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.15);\n            background: #19243a;\n        }',
    '.scenario-card:hover {\n            border-color: #0284c7;\n            transform: translateY(-2px);\n            box-shadow: 0 4px 8px rgba(2, 132, 199, 0.1);\n            background: #f0f9ff;\n        }'
)

html = html.replace(
    '.scenario-title {\n            font-size: 0.8rem;\n            font-weight: 600;\n            color: #f8fafc;\n        }',
    '.scenario-title {\n            font-size: 0.85rem;\n            font-weight: 700;\n            color: #0f172a;\n        }'
)

# 10. Pipeline Stepper
html = html.replace(
    '.pipeline-stepper {\n            background: #0f172a;',
    '.pipeline-stepper {\n            background: #f8fafc;'
)

html = html.replace(
    '.step-item {\n            background: #162032;\n            border: 1px solid var(--border-subtle);\n            border-radius: 6px;\n            padding: 6px 8px;\n            display: flex;\n            align-items: center;\n            gap: 6px;\n            font-size: 0.72rem;\n            color: var(--text-muted);',
    '.step-item {\n            background: #ffffff;\n            border: 1px solid var(--border-subtle);\n            border-radius: 6px;\n            padding: 6px 8px;\n            display: flex;\n            align-items: center;\n            gap: 6px;\n            font-size: 0.72rem;\n            color: #334155;'
)

html = html.replace(
    '.step-num {\n            width: 18px;\n            height: 18px;\n            border-radius: 50%;\n            background: #1e293b;\n            color: var(--text-secondary);',
    '.step-num {\n            width: 18px;\n            height: 18px;\n            border-radius: 50%;\n            background: #e2e8f0;\n            color: #475569;'
)

html = html.replace(
    '.step-item.active {\n            border-color: #38bdf8;\n            background: rgba(56, 189, 248, 0.1);\n            color: #38bdf8;\n        }',
    '.step-item.active {\n            border-color: #0284c7;\n            background: #eff6ff;\n            color: #0284c7;\n        }'
)

html = html.replace(
    '.step-item.active .step-num {\n            background: #38bdf8;\n            color: #0f172a;\n        }',
    '.step-item.active .step-num {\n            background: #0284c7;\n            color: #ffffff;\n        }'
)

html = html.replace(
    '.step-item.done {\n            border-color: #10b981;\n            background: rgba(16, 185, 129, 0.08);\n            color: #34d399;\n        }',
    '.step-item.done {\n            border-color: #059669;\n            background: #ecfdf5;\n            color: #047857;\n        }'
)

html = html.replace(
    '.step-item.done .step-num {\n            background: #10b981;\n            color: #0f172a;\n        }',
    '.step-item.done .step-num {\n            background: #059669;\n            color: #ffffff;\n        }'
)

# 11. Markdown rendered text & code blocks
html = html.replace(
    '.markdown-rendered {\n            font-size: 0.9rem;\n            line-height: 1.7;\n            color: #e2e8f0;\n        }',
    '''.markdown-rendered {
            font-size: 0.95rem;
            line-height: 1.75;
            color: #0f172a;
        }
        .markdown-rendered h1, .markdown-rendered h2, .markdown-rendered h3 {
            color: #0f172a !important;
            margin-top: 16px;
            margin-bottom: 8px;
            font-weight: 700;
        }
        .markdown-rendered h4 {
            color: #0284c7 !important;
            margin-top: 12px;
            margin-bottom: 6px;
            font-weight: 700;
        }
        .markdown-rendered p { margin-bottom: 10px; }
        .markdown-rendered ul, .markdown-rendered ol { padding-left: 22px; margin-bottom: 12px; }
        .markdown-rendered li { margin-bottom: 6px; }
        .markdown-rendered strong { color: #0f172a; font-weight: 700; }
        .markdown-rendered code {
            background: #f1f5f9 !important;
            color: #0f172a !important;
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid #e2e8f0;
            font-family: var(--font-mono);
            font-size: 0.85rem;
        }
        .markdown-rendered pre {
            background: #f8fafc !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 6px;
            padding: 14px;
            overflow-x: auto;
            margin: 12px 0;
            color: #0f172a !important;
        }
        .markdown-rendered pre code {
            background: transparent !important;
            border: none !important;
            color: #0f172a !important;
            padding: 0;
        }'''
)

# 12. Badges light mode
html = html.replace(
    '.badge-info { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }',
    '.badge-info { background: #eff6ff; color: #0284c7; border: 1px solid #bfdbfe; }'
)
html = html.replace(
    '.badge-success { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }',
    '.badge-success { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }'
)
html = html.replace(
    '.badge-warning { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }',
    '.badge-warning { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }'
)
html = html.replace(
    '.badge-danger { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }',
    '.badge-danger { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }'
)
html = html.replace(
    '.badge-purple { background: rgba(139, 92, 246, 0.2); color: #c084fc; border: 1px solid #8b5cf6; }',
    '.badge-purple { background: #f5f3ff; color: #6d28d9; border: 1px solid #ddd6fe; }'
)

# 13. Replace hardcoded inline backgrounds
html = html.replace('background:#111928;', 'background:#ffffff;')
html = html.replace('background:#111927;', 'background:#ffffff;')
html = html.replace('background:#0f172a;', 'background:#f8fafc;')
html = html.replace('background:#0d1527;', 'background:#ffffff;')
html = html.replace('background:#162032;', 'background:#ffffff;')
html = html.replace('background:#0b1120;', 'background:#f8fafc;')
html = html.replace('background: #0d1322;', 'background: #ffffff;')
html = html.replace('background:rgba(15, 23, 42, 0.6);', 'background:#f8fafc;')
html = html.replace('background: rgba(30, 41, 59, 0.6);', 'background:#f8fafc;')
html = html.replace('background:rgba(15, 23, 42, 0.7);', 'background:#f1f5f9;')
html = html.replace('background:rgba(0,0,0,0.75);', 'background:rgba(15,23,42,0.45);')

# Replace white text in inline styles
html = html.replace('color:#fff;', 'color:#0f172a;')
html = html.replace('color: #fff;', 'color: #0f172a;')
html = html.replace('color:#f8fafc;', 'color:#0f172a;')

# Make buttons retain crisp white text
html = html.replace(
    '.btn-primary {\n            background: var(--primary);\n            color: #fff;',
    '.btn-primary {\n            background: #0284c7;\n            color: #ffffff;'
)
html = html.replace(
    '.btn-success { background: #059669; color: #fff; }',
    '.btn-success { background: #059669; color: #ffffff; }'
)
html = html.replace(
    '.btn-danger { background: #b91c1c; color: #fff; }',
    '.btn-danger { background: #dc2626; color: #ffffff; }'
)
html = html.replace(
    '.btn-secondary {\n            background: var(--bg-elevated);\n            color: var(--text-secondary);',
    '.btn-secondary {\n            background: #f1f5f9;\n            color: #334155;\n            border-color: #cbd5e1;'
)

# Fix brand logo
html = html.replace(
    '.brand-logo {\n            width: 32px;\n            height: 32px;\n            background: linear-gradient(135deg, #0284c7, #6366f1);\n            border-radius: 8px;\n            display: flex;\n            align-items: center;\n            justify-content: center;\n            color: #fff;',
    '.brand-logo {\n            width: 32px;\n            height: 32px;\n            background: linear-gradient(135deg, #0284c7, #6366f1);\n            border-radius: 8px;\n            display: flex;\n            align-items: center;\n            justify-content: center;\n            color: #ffffff;'
)

# Fix answer card styling
html = html.replace(
    'id="ai-answer-card" style="display:none; background:#ffffff; border:1px solid #1e293b; border-left:4px solid #38bdf8;',
    'id="ai-answer-card" style="display:none; background:#ffffff; border:1px solid #bfdbfe; border-left:5px solid #0284c7; box-shadow:0 4px 14px rgba(2,132,199,0.08);'
)

# Fix dropzone
html = html.replace(
    'id="upload-dropzone" style="border:2px dashed #3b82f6; border-radius:8px; padding:24px; text-align:center; background:#f8fafc; cursor:pointer; margin-bottom:16px;"',
    'id="upload-dropzone" style="border:2px dashed #0284c7; border-radius:8px; padding:24px; text-align:center; background:#f8fafc; cursor:pointer; margin-bottom:16px;"'
)

# 14. Add Mission & Workflow Banner right into panel-ai-run
workflow_banner = '''
                    <!-- Project Architecture & System Workflow Banner -->
                    <div style="background: linear-gradient(135deg, #eff6ff, #f0fdf4); border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px 20px; margin-bottom: 18px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                            <span style="font-weight:700; color:#0369a1; font-size:0.95rem;">
                                <i class="fa-solid fa-circle-nodes"></i> How ServerGen AI Operates (End-to-End Enterprise Flow):
                            </span>
                            <span class="badge badge-success"><i class="fa-solid fa-lock"></i> 100% On-Premise &bull; Zero Cloud Leakage</span>
                        </div>
                        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap:10px; font-size:0.8rem; color:#334155; margin-top:10px;">
                            <div style="background:#ffffff; padding:12px; border-radius:6px; border:1px solid #e2e8f0; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                                <div style="font-weight:700; color:#0284c7; margin-bottom:4px;"><i class="fa-solid fa-file-import"></i> 1. Document Ingestion</div>
                                <div style="color:#64748b; font-size:0.75rem;">Upload PDFs, scanned images (Native OCR), DOCX, TXT. Embedded locally.</div>
                            </div>
                            <div style="background:#ffffff; padding:12px; border-radius:6px; border:1px solid #e2e8f0; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                                <div style="font-weight:700; color:#0284c7; margin-bottom:4px;"><i class="fa-solid fa-shield-halved"></i> 2. Clearance Gate</div>
                                <div style="color:#64748b; font-size:0.75rem;">RBAC strictly restricts retrieval by clearance (Public, Internal, Confidential, Restricted).</div>
                            </div>
                            <div style="background:#ffffff; padding:12px; border-radius:6px; border:1px solid #e2e8f0; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                                <div style="font-weight:700; color:#0284c7; margin-bottom:4px;"><i class="fa-solid fa-brain"></i> 3. Local LLM (Ollama)</div>
                                <div style="color:#64748b; font-size:0.75rem;">Local llama3.2:3b synthesizes responses solely from retrieved evidence.</div>
                            </div>
                            <div style="background:#ffffff; padding:12px; border-radius:6px; border:1px solid #e2e8f0; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                                <div style="font-weight:700; color:#0284c7; margin-bottom:4px;"><i class="fa-solid fa-fingerprint"></i> 4. Verified Citations & Audit</div>
                                <div style="color:#64748b; font-size:0.75rem;">Every claim is matched against sources and hashed into an immutable SHA-256 audit ledger.</div>
                            </div>
                        </div>
                    </div>
'''

if '<!-- Project Architecture & System Workflow Banner -->' not in html:
    html = html.replace(
        '<div class="card-desc">\n                        Full zero-trust pipeline: RBAC Authorization &rarr; Task Classification &rarr; Sensitivity Rating &rarr; Composite Risk Scoring &rarr; Security Policy Check &rarr; Tool/Ollama Execution &rarr; Output Sanitization &rarr; Audit Ledger.\n                    </div>',
        '<div class="card-desc">\n                        Full zero-trust pipeline: RBAC Authorization &rarr; Task Classification &rarr; Sensitivity Rating &rarr; Composite Risk Scoring &rarr; Security Policy Check &rarr; Tool/Ollama Execution &rarr; Output Sanitization &rarr; Audit Ledger.\n                    </div>' + workflow_banner
    )

with open('test-interface.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Successfully modernized test-interface.html to Light Enterprise Theme!')
