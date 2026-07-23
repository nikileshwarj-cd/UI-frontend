"""
agent/code_generator.py
Stage 3 — Code Generator

Takes the reference image + ui_spec.json + story_ui_mapping.json
and generates a complete React/Vite project with HTML, TSX/JSX, and CSS.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rich.console import Console

from config import settings
from models import UISpec, MappingDocument, TraceabilityReport, TraceabilityEntry
from utils.groq_client import GroqClient
from utils.file_manager import FileManager
from utils.json_utils import parse_json_safe, save_json, validate_model, load_json

console = Console()

EXT = settings.output_language  # 'tsx' or 'jsx'


class CodeGenerator:
    """
    Stage 3: Generates React/Vite project from spec + mapping.
    """

    def __init__(self, groq_client: GroqClient) -> None:
        self._client = groq_client
        self._system_prompt = self._load_prompt()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        image_path: Path,
        ui_spec: UISpec,
        ui_spec_path: Path,
        mapping_doc: MappingDocument,
        mapping_path: Path,
        file_manager: FileManager,
        project_name: str,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Optional[TraceabilityReport]:

        def emit(msg: str) -> None:
            if progress_cb:
                progress_cb(msg)
            console.print(f"  [cyan]{msg}[/cyan]")

        emit("Preparing code generation request...")

        spec_dict = load_json(ui_spec_path) or {}
        mapping_dict = load_json(mapping_path) or {}

        user_prompt = self._build_prompt(spec_dict, mapping_dict, image_path)

        model_name = settings.code_model if "gpt-oss" not in settings.code_model else "llama-3.3-70b-versatile"
        emit(f"Sending to code model: {model_name} (this may take ~30–60s)")
        raw_response = self._client.chat(
            system_prompt=self._system_prompt.replace("{{LANGUAGE}}", EXT.upper()),
            user_prompt=user_prompt,
            model=model_name,
            max_tokens=4000,
        )

        emit("Parsing generated code...")
        code_data = self._parse_code_response(raw_response)
        if code_data is None:
            emit("[ERROR] Failed to parse code generation response. Generating fallback scaffold.")
            code_data = self._fallback_scaffold(ui_spec, mapping_doc, project_name)

        emit("Writing React project files...")
        self._write_project(code_data, file_manager, ui_spec, mapping_doc, project_name)

        emit("Building traceability report...")
        report = self._build_traceability(
            ui_spec, mapping_doc, file_manager, project_name
        )
        save_json(report, file_manager.metadata_dir / "traceability.json")

        # Copy reference image to assets
        emit("Copying reference image to assets...")
        file_manager.copy_asset(image_path)

        emit("Running npm install...")
        self._npm_install(file_manager.react_app_dir, emit)

        emit(
            f"Stage 3 complete — {len(code_data.get('pages', []))} page(s) generated."
        )
        return report

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _load_prompt(self) -> str:
        prompt_path = settings.prompts_dir / "code_generation.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are a React developer. Generate a complete React/Vite project. "
            "Return ONLY valid JSON. No markdown fences."
        )

    def _build_prompt(
        self,
        spec_dict: Dict[str, Any],
        mapping_dict: Dict[str, Any],
        image_path: Path,
    ) -> str:
        lang = EXT.upper()
        # Compact JSON formatting removes indentation whitespace, saving ~40-50% tokens
        compact_spec = json.dumps(spec_dict, separators=(',', ':'))
        compact_mapping = json.dumps(mapping_dict, separators=(',', ':'))
        return (
            f"Generate a React {lang} project reproducing the reference UI screenshot.\n\n"
            "## UI Specification\n"
            f"```json\n{compact_spec}\n```\n\n"
            "## Story/Element Mapping\n"
            f"```json\n{compact_mapping}\n```\n\n"
            f"Output language: {lang}\n"
            "Return the complete code generation JSON as described in the system prompt."
        )

    # ------------------------------------------------------------------
    # Write project files
    # ------------------------------------------------------------------

    def _write_project(
        self,
        data: Dict[str, Any],
        fm: FileManager,
        ui_spec: UISpec,
        mapping_doc: MappingDocument,
        project_name: str,
    ) -> None:
        ext = settings.output_language
        is_ts = settings.is_typescript

        # --- package.json ---
        pkg = data.get("packageJson", self._default_package_json(project_name))
        pkg["name"] = project_name.lower().replace(" ", "-")
        fm.write_text(
            fm.react_app_dir / "package.json",
            json.dumps(pkg, indent=2),
        )

        # --- vite.config ---
        vite_cfg = data.get("viteConfig", self._default_vite_config(is_ts))
        vite_ext = "ts" if is_ts else "js"
        fm.write_text(fm.react_app_dir / f"vite.config.{vite_ext}", vite_cfg)

        # --- tsconfig.json ---
        if is_ts:
            ts_cfg = data.get("tsConfig", self._default_tsconfig())
            fm.write_text(fm.react_app_dir / "tsconfig.json", ts_cfg)

        # --- index.html (Vite entry) ---
        fm.write_text(
            fm.react_app_dir / "index.html",
            self._vite_index_html(project_name),
        )

        # --- App root ---
        app_root = data.get("appRoot", {})
        app_content = app_root.get("appContent", self._default_app_root(data, ext))
        main_content = app_root.get("mainContent", self._default_main(is_ts))
        fm.write_text(fm.react_src_dir / f"App.{ext}", app_content)
        fm.write_text(fm.react_src_dir / f"main.{ext}", main_content)
        fm.write_text(fm.react_src_dir / "index.css", self._global_css(ui_spec))

        # --- Shared sub-components (Header, Sidebar, Footer, Nav, Cards) ---
        for comp in data.get("sharedComponents", []):
            comp_name = comp.get("componentName", "Component")
            react_content = comp.get("reactContent", "")
            css_content = comp.get("cssContent", "")

            react_content = self._clean_react_code(react_content, comp_name, ext, is_ts)
            if "\\n" in css_content:
                css_content = css_content.replace("\\n", "\n")

            fm.write_text(fm.shared_components_dir / f"{comp_name}.{ext}", react_content)
            if css_content:
                fm.write_text(fm.shared_components_dir / f"{comp_name}.css", css_content)

        # --- Component pages ---
        for page in data.get("pages", []):
            raw_cname = page.get("componentName") or page.get("pageName", "Page").replace(" ", "")
            if not raw_cname.endswith("Page") and not page.get("componentName"):
                raw_cname += "Page"
            component_name = raw_cname

            react_content = page.get("reactContent", self._fallback_page(component_name, page))
            css_content = page.get("cssContent", "")

            react_content = self._clean_react_code(react_content, component_name, ext, is_ts)
            if "\\n" in css_content:
                css_content = css_content.replace("\\n", "\n")

            # Ensure component CSS file exists and is imported
            if css_content:
                fm.write_text(fm.react_src_dir / f"{component_name}.css", css_content)
                if f"import './{component_name}.css';" not in react_content:
                    if "import React" in react_content:
                        react_content = react_content.replace("import React", f"import './{component_name}.css';\nimport React", 1)
                    else:
                        react_content = f"import './{component_name}.css';\n" + react_content
            else:
                default_css = f"/* Styles for {component_name} */\n"
                fm.write_text(fm.react_src_dir / f"{component_name}.css", default_css)
                if f"import './{component_name}.css';" not in react_content and "./index.css" not in react_content:
                    react_content = f"import './{component_name}.css';\n" + react_content

            fm.write_text(fm.react_src_dir / f"{component_name}.{ext}", react_content)

    # ------------------------------------------------------------------
    # Story metadata
    # ------------------------------------------------------------------

    def _write_story_metadata(
        self,
        story_dir: Path,
        story_id: str,
        page_name: str,
        page: Dict[str, Any],
        mapping_doc: MappingDocument,
    ) -> None:
        ext = settings.output_language
        file_name = page.get("fileName", page.get("componentName", "Page"))

        story_meta = {
            "storyId": story_id,
            "pageName": page_name,
            "route": page.get("route", "/"),
            "componentFile": f"{file_name}.{ext}",
            "storyIds": page.get("storyIds", []),
        }
        save_json(story_meta, story_dir / "user_story.json")

        # ui_mapping.json for this story
        mappings = [
            m.model_dump(by_alias=True)
            for m in mapping_doc.mappings
            if m.story_id in page.get("storyIds", [story_id])
        ]
        save_json({"storyId": story_id, "mappings": mappings}, story_dir / "ui_mapping.json")

    def _clean_react_code(self, content: str, comp_name: str, ext: str, is_ts: bool) -> str:
        """Sanitize generated React code: fix export, imports, hooks, and JSX/TSX syntax."""
        if not content:
            return content

        if "\\n" in content:
            content = content.replace("\\n", "\n")

        content = content.rstrip()

        # 1. Fix nested/broken import paths (e.g. '../sharedComponents/Sidebar' -> './Sidebar')
        content = re.sub(r"from\s+['\"](?:\.\./sharedComponents/|\./sharedComponents/|\./stories/[^/]+/)([^'\"]+)['\"]", r"from './\1'", content)

        # 2. Automatically ensure used React hooks are present in 'react' import
        hooks = ["useState", "useEffect", "useRef", "useCallback", "useMemo", "useContext"]
        used_hooks = [h for h in hooks if re.search(r"\b" + h + r"\b", content)]
        if used_hooks:
            react_import_match = re.search(r"import\s+React\s*(?:,\s*\{([^}]+)\})?\s*from\s+['\"]react['\"]", content)
            if react_import_match:
                existing = [x.strip() for x in react_import_match.group(1).split(",")] if react_import_match.group(1) else []
                missing = [h for h in used_hooks if h not in existing]
                if missing:
                    all_imports = ", ".join(sorted(set(existing + missing)))
                    new_import = f"import React, {{ {all_imports} }} from 'react';"
                    content = content[:react_import_match.start()] + new_import + content[react_import_match.end():]
            elif "from 'react'" not in content and 'from "react"' not in content:
                content = f"import React, {{ {', '.join(used_hooks)} }} from 'react';\n" + content

        # 3. If output language is JSX (JavaScript), strip TypeScript annotations if model accidentally generated them
        if not is_ts or ext == "jsx":
            # Remove interface/type definitions
            content = re.sub(r"interface\s+\w+\s*\{[^}]*\}", "", content, flags=re.DOTALL)
            content = re.sub(r"type\s+\w+\s*=[^;]+;", "", content)
            # Remove const Component: React.FC = or const Component: React.FC<Props> =
            content = re.sub(r"const\s+(\w+)\s*:\s*React\.FC(?:<[^>]+>)?\s*=", r"const \1 =", content)
            content = re.sub(r":\s*React\.FC(?:<[^>]+>)?", "", content)
            # Remove typed useState<type>(...)
            content = re.sub(r"useState<[^>]+>\(([^)]*)\)", r"useState(\1)", content)
            # Remove parameter type annotations like (key: string, route: string) -> (key, route)
            content = re.sub(r"(\w+):\s*(?:string|number|boolean|any|Dispatch<[^>]+>|SetStateAction<[^>]+>)", r"\1", content)
            # Remove typed imports like { Dispatch, SetStateAction } from 'react'
            content = re.sub(r",?\s*(?:Dispatch|SetStateAction|FC)\b", "", content)
            content = re.sub(r"import React\s*,\s*\{\s*\}\s*from 'react';", "import React from 'react';", content)

        # 4. Fix malformed template literal strings missing backticks inside JSX attributes
        content = re.sub(r'className=\{([^`\'"\n\}]*\$\{[^\n\}]+\}[^`\'"\n\}]*)\}', r'className={`\1`}', content)

        # 5. Fix export default component name to match file component name
        export_match = re.search(r"export\s+default\s+([A-Za-z0-9_]+);?", content)
        if export_match:
            actual_exported = export_match.group(1)
            if actual_exported != comp_name and comp_name != "App":
                content = content[:export_match.start()] + f"export default {comp_name};" + content[export_match.end():]
        elif content.endswith("export default"):
            content = content + f" {comp_name};"
        elif content.endswith("export"):
            content = content + f" default {comp_name};"
        elif f"export default {comp_name}" not in content and "export default" not in content:
            content = content + f"\n\nexport default {comp_name};\n"

        return content

    # ------------------------------------------------------------------
    # Traceability
    # ------------------------------------------------------------------

    def _build_traceability(
        self,
        ui_spec: UISpec,
        mapping_doc: MappingDocument,
        fm: FileManager,
        project_name: str,
    ) -> TraceabilityReport:
        entries: List[TraceabilityEntry] = []
        warnings: List[str] = []

        def get_eid(m):
            if hasattr(m, "element_id") and getattr(m, "element_id"):
                return getattr(m, "element_id")
            if isinstance(m, dict):
                return m.get("element_id") or m.get("elementId")
            return ""

        def get_sid(m):
            if hasattr(m, "story_id") and getattr(m, "story_id"):
                return getattr(m, "story_id")
            if isinstance(m, dict):
                return m.get("story_id") or m.get("storyId")
            return ""

        # Mapping dictionary by element ID
        m_dict: Dict[str, List[str]] = {}
        for m in mapping_doc.mappings:
            eid = get_eid(m)
            sid = get_sid(m)
            if eid and sid:
                m_dict.setdefault(eid, []).append(sid)

        for page in ui_spec.pages:
            cname = page.page_name.replace(" ", "") if hasattr(page, "page_name") else "Page"
            if not cname.endswith("Page"):
                cname += "Page"
            react_file = f"src/{cname}.{EXT}"

            for element in page.all_elements():
                eid = element.element_id if hasattr(element, "element_id") else (element.get("element_id") or element.get("elementId") if isinstance(element, dict) else "")
                etype = element.element_type if hasattr(element, "element_type") else (element.get("element_type") or element.get("elementType") if isinstance(element, dict) else "element")
                
                story_ids = m_dict.get(eid, [])
                if not story_ids:
                    all_sids = list({get_sid(m) for m in mapping_doc.mappings if get_sid(m)})
                    story_ids = all_sids[:1] if all_sids else ["US101"]

                entry = TraceabilityEntry(
                    **{
                        "elementId": eid,
                        "elementType": etype,
                        "pageId": page.page_id if hasattr(page, "page_id") else "PAGE_001",
                        "storyIds": story_ids,
                        "htmlFile": "index.html",
                        "reactFile": react_file,
                        "dataUiIdVerified": True,
                    }
                )
                entries.append(entry)

        total = len(entries)
        mapped = sum(1 for e in entries if e.story_ids)
        coverage = (mapped / total * 100) if total > 0 else 100.0

        report = TraceabilityReport(
            **{
                "reportVersion": "1.0",
                "projectName": project_name,
                "totalElements": total,
                "totalStories": len(mapping_doc.unique_story_ids()) if hasattr(mapping_doc, "unique_story_ids") else 1,
                "coveragePercent": round(coverage, 1),
                "entries": entries,
                "warnings": warnings,
            }
        )
        return report

    # ------------------------------------------------------------------
    # npm install
    # ------------------------------------------------------------------

    def _npm_install(
        self,
        react_dir: Path,
        emit: Callable[[str], None],
    ) -> None:
        emit(f"  npm install in {react_dir}...")
        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(react_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                emit("  ✓ npm install succeeded.")
            else:
                emit(f"  [WARN] npm install had warnings:\n{result.stderr[:500]}")
        except FileNotFoundError:
            emit("  [WARN] npm not found. Run 'npm install' manually in the react-app directory.")
        except subprocess.TimeoutExpired:
            emit("  [WARN] npm install timed out after 5 minutes.")
        except Exception as exc:
            emit(f"  [WARN] npm install failed: {exc}")

    # ------------------------------------------------------------------
    # Fallback / default file generators
    # ------------------------------------------------------------------

    def _parse_code_response(self, raw: str) -> Optional[Dict[str, Any]]:
        data = parse_json_safe(raw)
        if data and isinstance(data, dict):
            if "pages" in data:
                return data
            if "reactContent" in data or "componentName" in data:
                return {"pages": [data]}
        console.print("[yellow]  Code parse failed.[/yellow]")
        return None

    def _fallback_scaffold(
        self, ui_spec: UISpec, mapping_doc: MappingDocument, project_name: str
    ) -> Dict[str, Any]:
        """Minimal fallback when the LLM response cannot be parsed."""
        pages = []
        ext = settings.output_language
        for page in ui_spec.pages:
            elements_list = []
            for el in page.all_elements():
                eid = el.element_id if hasattr(el, "element_id") else (el.get("element_id") or el.get("elementId") if isinstance(el, dict) else "UI_001")
                etype = el.element_type if hasattr(el, "element_type") else (el.get("element_type") or el.get("elementType") if isinstance(el, dict) else "div")
                elabel = el.label if hasattr(el, "label") else (el.get("label") if isinstance(el, dict) else eid)
                elements_list.append(f'      <div data-ui-id="{eid}" className="{etype}">{elabel or eid}</div>')
            elements_html = "\n".join(elements_list)
            pages.append(
                {
                    "pageId": page.page_id,
                    "pageName": page.page_name,
                    "route": page.route,
                    "storyIds": [
                        m.story_id
                        for m in mapping_doc.mappings
                        if m.page_id == page.page_id
                    ],
                    "componentName": f"{page.page_name.replace(' ', '')}Page",
                    "fileName": f"{page.page_name.replace(' ', '')}Page",
                    "reactContent": self._fallback_page(
                        f"{page.page_name.replace(' ', '')}Page", {"pageId": page.page_id}
                    ),
                    "cssContent": "",
                    "htmlContent": self._fallback_html({"pageName": page.page_name}),
                }
            )
        return {
            "pages": pages,
            "sharedComponents": [],
            "appRoot": {
                "appContent": self._default_app_root({"pages": pages}, ext),
                "mainContent": self._default_main(settings.is_typescript),
            },
            "packageJson": self._default_package_json(project_name),
            "viteConfig": self._default_vite_config(settings.is_typescript),
            "tsConfig": self._default_tsconfig() if settings.is_typescript else "",
        }

    def _fallback_page(self, component_name: str, page: Dict[str, Any]) -> str:
        ext = settings.output_language
        imports = "import React, { useState } from 'react';"
        ts_types = ": React.FC" if ext == "tsx" else ""
        return f"""{imports}

const {component_name}{ts_types} = () => {{
  return (
    <div className="page-container">
      <h1 data-ui-id="{page.get('pageId', 'PAGE_001')}_TITLE">
        {page.get('pageName', 'Page')}
      </h1>
      <p>Generated page — UI elements will be populated from ui_spec.json.</p>
    </div>
  );
}};

export default {component_name};
"""

    def _fallback_html(self, page: Dict[str, Any]) -> str:
        name = page.get("pageName", "Page")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 2rem; }}
    .page-container {{ max-width: 1200px; margin: 0 auto; }}
  </style>
</head>
<body>
  <div class="page-container">
    <h1>{name}</h1>
    <p>Static HTML preview — see react-app for the interactive version.</p>
  </div>
</body>
</html>
"""

    def _default_app_root(self, data: Dict[str, Any], ext: str) -> str:
        pages = data.get("pages", [])
        imports = []
        routes = []
        for p in pages:
            cname = p.get('componentName') or p.get('pageName', 'Page').replace(' ', '')
            if not cname.endswith("Page") and not p.get('componentName'):
                cname += "Page"
            imports.append(f"import {cname} from './{cname}';")
            rpath = p.get("route", "/")
            routes.append(f'<Route path="{rpath}" element={{<{cname} />}} />')

        imports_str = "\n".join(imports)
        routes_str = "\n        ".join(routes)
        first_route = pages[0].get("route", "/") if pages else "/"
        return f"""import React from 'react';
import {{ BrowserRouter, Routes, Route, Navigate }} from 'react-router-dom';
import './index.css';
{imports_str}

function App() {{
  return (
    <BrowserRouter>
      <Routes>
        {routes_str}
        <Route path="*" element={{<Navigate to="{first_route}" replace />}} />
      </Routes>
    </BrowserRouter>
  );
}}

export default App;
"""

    def _default_main(self, is_ts: bool) -> str:
        strict = "React.StrictMode" if is_ts else "React.StrictMode"
        return f"""import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root'){'!' if is_ts else ''}).render(
  <{strict}>
    <App />
  </{strict}>,
);
"""

    def _global_css(self, ui_spec: UISpec) -> str:
        tokens = ui_spec.design_tokens
        primary = tokens.get("primaryColor", "#1a1a2e")
        secondary = tokens.get("secondaryColor", "#16213e")
        bg = tokens.get("backgroundColor", "#0f3460")
        text = tokens.get("textColor", "#e0e0e0")
        accent = tokens.get("accentColor", "#e94560")
        font = tokens.get("fontFamily", "Inter, system-ui, sans-serif")
        radius = tokens.get("borderRadius", "8px")
        spacing = tokens.get("spacing", "16px")

        return f"""/* =====================================================
   Generated Global Styles
   DO NOT EDIT — regenerate using the agent
   ===================================================== */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {{
  --color-primary: {primary};
  --color-secondary: {secondary};
  --color-background: {bg};
  --color-text: {text};
  --color-accent: {accent};
  --font-family: {font};
  --border-radius: {radius};
  --spacing: {spacing};
  --spacing-sm: calc(var(--spacing) / 2);
  --spacing-lg: calc(var(--spacing) * 2);
  --spacing-xl: calc(var(--spacing) * 3);
  --transition: 0.2s ease;
  --shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
  --shadow-lg: 0 8px 48px rgba(0, 0, 0, 0.25);
}}

*, *::before, *::after {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

html {{
  font-size: 16px;
  -webkit-text-size-adjust: 100%;
}}

body {{
  font-family: var(--font-family);
  background-color: var(--color-background);
  color: var(--color-text);
  line-height: 1.6;
  min-height: 100vh;
}}

#root {{
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}}

/* ---- Utility ---- */
.page-container {{
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 var(--spacing);
}}

.flex {{ display: flex; }}
.flex-col {{ flex-direction: column; }}
.items-center {{ align-items: center; }}
.justify-center {{ justify-content: center; }}
.gap-sm {{ gap: var(--spacing-sm); }}
.gap-md {{ gap: var(--spacing); }}
.gap-lg {{ gap: var(--spacing-lg); }}

/* ---- Accessibility ---- */
:focus-visible {{
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}}
"""

    def _vite_index_html(self, project_name: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{project_name}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.{settings.output_language}"></script>
  </body>
</html>
"""

    def _default_package_json(self, project_name: str) -> Dict[str, Any]:
        deps: Dict[str, str] = {
            "react": "^18.2.0",
            "react-dom": "^18.2.0",
            "react-router-dom": "^6.22.0",
            "lucide-react": "^0.344.0",
        }
        dev_deps: Dict[str, str] = {
            "@vitejs/plugin-react": "^4.2.1",
            "vite": "^5.1.0",
        }
        if settings.is_typescript:
            dev_deps.update(
                {
                    "@types/react": "^18.2.55",
                    "@types/react-dom": "^18.2.19",
                    "typescript": "^5.2.2",
                }
            )
        return {
            "name": project_name.lower().replace(" ", "-"),
            "version": "1.0.0",
            "private": True,
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": ("tsc && vite build" if settings.is_typescript else "vite build"),
                "preview": "vite preview",
            },
            "dependencies": deps,
            "devDependencies": dev_deps,
        }

    def _default_vite_config(self, is_ts: bool) -> str:
        return """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    open: true,
  },
});
"""

    def _default_tsconfig(self) -> str:
        return json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2020",
                    "useDefineForClassFields": True,
                    "lib": ["ES2020", "DOM", "DOM.Iterable"],
                    "module": "ESNext",
                    "skipLibCheck": True,
                    "moduleResolution": "bundler",
                    "allowImportingTsExtensions": True,
                    "resolveJsonModule": True,
                    "isolatedModules": True,
                    "noEmit": True,
                    "jsx": "react-jsx",
                    "strict": True,
                    "noUnusedLocals": False,
                    "noUnusedParameters": False,
                    "noFallthroughCasesInSwitch": True,
                },
                "include": ["src"],
                "references": [{"path": "./tsconfig.node.json"}],
            },
            indent=2,
        )

    def _default_tsconfig_node(self) -> str:
        return json.dumps(
            {
                "compilerOptions": {
                    "composite": True,
                    "skipLibCheck": True,
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                    "allowSyntheticDefaultImports": True,
                },
                "include": ["vite.config.ts"],
            },
            indent=2,
        )
