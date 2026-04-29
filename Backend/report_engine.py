"""
Report Automation Engine — The synthesis layer for Adept.

Orchestrates:
1. Question Wizard logic (schemas).
2. Hybrid Retrieval (Qdrant + Elasticsearch).
3. Gemini-powered section synthesis.
4. DOCX Assembly.
"""

import os
import json
import logging
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from docxtpl import DocxTemplate
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
# from agent_manager import call_gemini_sync # Moved to methods to prevent import stall

logger = logging.getLogger(__name__)

# --- Environment Context ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
# ES context removed

# --- Report Type Abstraction ---
REPORT_TYPES = {
    "sprint": {
        "title": "Sprint Review Report",
        "sections": [
            {
                "id": "metadata",
                "title": "Document Information",
                "questions": [
                    {"id": "project_name", "label": "Project Name", "type": "text"},
                    {"id": "report_by", "label": "Prepared By", "type": "text"},
                    {"id": "sprint_no", "label": "Sprint Number", "type": "number"},
                    {"id": "period", "label": "Reporting Date", "type": "date"},
                    {"id": "sprint_goal", "label": "Sprint Goal", "type": "textarea"},
                    {"id": "sprint_scope", "label": "Sprint Scope", "type": "textarea"}
                ]
            },
            {
                "id": "intro",
                "title": "Introduction",
                "questions": [
                    {"id": "executive_summary", "label": "Executive Summary", "type": "textarea"}
                ],
                "retrieval_query": "adept report introduction standards executive summary"
            },
            {
                "id": "status",
                "title": "Overall Status",
                "questions": [
                    {"id": "status_rating", "label": "Overall Status", "type": "dropdown", "options": ["Delayed", "On Track", "Ahead"]},
                    {"id": "summary_text", "label": "High-Level Summary", "type": "textarea"},
                    {"id": "timeline", "label": "Timeline (e.g. 4th - 15th Aug)", "type": "text"},
                    {"id": "time_spent", "label": "Time Spent Total", "type": "text"}
                ],
                "retrieval_query": "how to write executive summary adept status report standards"
            },
            {
                "id": "progress_detail",
                "title": "Progress",
                "questions": [
                    {"id": "tasks_completed", "label": "Key Accomplishments", "type": "list"}
                ],
                "retrieval_query": "adept progress reporting guidelines"
            },
            {
                "id": "next_sprint",
                "title": "Next Sprint Priority",
                "questions": [
                    {"id": "future_tasks", "label": "Upcoming Priorities", "type": "list"}
                ],
                "retrieval_query": "adept future planning standards"
            },
            {
                "id": "qa",
                "title": "QA",
                "questions": [
                    {"id": "qa_metrics", "label": "QA Metrics & Findings", "type": "textarea"},
                    {"id": "test_results", "label": "Key Test Results", "type": "list"}
                ],
                "retrieval_query": "adept QA reporting standards testing metrics"
            },
            {
                "id": "issues",
                "title": "Issues & Blockers",
                "questions": [
                    {"id": "issue_list", "label": "Current Blockers", "type": "list"}
                ],
                "retrieval_query": "adept standard for reporting risks issues blockers and impact"
            },
            {
                "id": "next_steps",
                "title": "Approvals needed",
                "questions": [
                    {"id": "pending_approvals", "label": "Required Approvals", "type": "list"}
                ],
                "retrieval_query": "adept governance approval process"
            }
        ],
        "docx_template": "report_templates/sprint_report.docx",
        "transformations": {
            "make_executive": "Rewrite this section for an executive audience.",
            "clarify": "Improve the clarity and flow.",
            "shorten": "Condense significantly."
        }
    },
    "marketing": {
        "title": "Marketing Performance Report",
        "sections": [
            {
                "id": "metadata",
                "title": "Document Information",
                "questions": [
                    {"id": "campaign_name", "label": "Campaign Name", "type": "text"},
                    {"id": "report_by", "label": "Prepared By", "type": "text"},
                    {"id": "period", "label": "Reporting Period", "type": "text"},
                    {"id": "target_audience", "label": "Target Audience", "type": "text"}
                ]
            },
            {
                "id": "performance",
                "title": "Execution & Performance",
                "questions": [
                    {"id": "kpis", "label": "Key Performance Metrics", "type": "textarea"}
                ],
                "retrieval_query": "marketing performance reporting standards campaign metrics"
            }
        ],
        "docx_template": "report_templates/marketing_report.docx",
        "transformations": {
            "make_executive": "Rewrite this section for an executive audience, highlighting key metrics.",
            "clarify": "Improve the clarity and flow of these performance points.",
            "shorten": "Condense this performance report significantly."
        }
    },
    "weekly": {
        "title": "Weekly Activity Report",
        "sections": [
            {
                "id": "metadata",
                "title": "Metadata",
                "questions": [
                    {"id": "week_of", "label": "Week Starting", "type": "date"},
                    {"id": "team_lead", "label": "Team Lead", "type": "text"}
                ]
            },
            {
                "id": "activities",
                "title": "Weekly Highlights",
                "questions": [
                    {"id": "highlights", "label": "Major Wins", "type": "textarea"}
                ],
                "retrieval_query": "weekly reporting cadence highlights wins"
            }
        ],
        "docx_template": "report_templates/weekly_report.docx",
        "transformations": {
            "make_executive": "Rewrite this weekly highlights section for an executive audience.",
            "clarify": "Improve the clarity of these weekly activities.",
            "shorten": "Condense the weekly wins significantly."
        }
    },
    "monthly": {
        "title": "Monthly Strategic Overview",
        "sections": [
            {
                "id": "metadata",
                "title": "Metadata",
                "questions": [
                    {"id": "month_year", "label": "Month & Year", "type": "text"},
                    {"id": "author", "label": "Report Author", "type": "text"}
                ]
            },
            {
                "id": "strategy",
                "title": "Strategic Gains",
                "questions": [
                    {"id": "gains", "label": "Monthly Progress", "type": "textarea"}
                ],
                "retrieval_query": "monthly strategic report template gains strategy"
            }
        ],
        "docx_template": "report_templates/monthly_report.docx",
        "transformations": {
            "make_executive": "Rewrite this strategic overview for an executive audience, focusing on impact.",
            "clarify": "Improve the clarity and flow of these strategic gains.",
            "shorten": "Condense this monthly strategic summary significantly."
        }
    }
}


class ReportAutomationEngine:
    def __init__(self):
        self._qdrant = None
    
    @property
    def qdrant(self):
        if self._qdrant is None:
            logger.info(f"Initializing Qdrant Client at {QDRANT_HOST}:{QDRANT_PORT}")
            self._qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        return self._qdrant


    def _sanitize_markdown(self, text):
        if not text: return ""
        import re
        # Remove Markdown headers (levels 1-6) only at the start of lines
        text = re.sub(r'^\s*#{1,6}\s+', '', text, flags=re.MULTILINE)
        return text.strip()

    def generate_report_draft(self, report_type, answers):
        """
        Builds the report section-by-section using the Wizard answers.
        Uses Parallel Execution to generate all sections simultaneously.
        """
        if report_type not in REPORT_TYPES:
            raise ValueError(f"Unknown report type: {report_type}")

        config = REPORT_TYPES[report_type]
        metadata = {
            "type": report_type,
            "title": config['title'],
            "sections": []
        }

        # --- Helper Function for Parallel Synthesis ---
        def process_section(section):
            section_id = section['id']
            if section_id == 'metadata':
                return section_id, None

            # Retrieve context (Guidelines)
            query = section.get('retrieval_query', section['title'])
            context = self.retrieve_filtered_context(query, doc_type="guideline")
            context_text = context.get('text', "")
            
            # Extract relevant user answers
            section_answers = {q['id']: answers.get(q['id']) for q in section['questions']}
            section_index = config['sections'].index(section)

            prompt = f"""
            You are the Adept Report Synthesizer.
            Your goal is to transform rough user updates into high-quality professional report content in a sharp, consulting-grade style.
            
            --- ADEPT GUIDELINES & STANDARDS ---
            {context_text}
            
            --- USER UPDATES FOR {section['title'].upper()} ---
            {json.dumps(section_answers, indent=2)}
            
            --- TASK ---
            Write the {section['title']} section for the {config['title']}.
            1. Use professional, active voice.
            2. Follow the tone and formatting logic found in the guidelines.
            3. Use systematic sub-section numbering: {section_index}.1, {section_index}.2, etc. 
               EVERY major topic MUST be a numbered sub-heading, not a bullet point.
            4. Use Markdown Tables for structured data (CRITICAL). 
            
            --- CRITICAL FORMATTING RULES ---
            - NO Markdown headers (#). Use the {section_index}.X numbering for headings.
            - Bolding is allowed for the numbered sub-headings.
            - Do NOT include the main section title anywhere in your response.
            - Output 'N/A' for missing data.
            - Use double newlines between sub-sections.
            - Ensure Markdown tables are valid (correct number of pipes and dashes).
            """
            
            from agent_manager import call_gemini_sync
            logger.info(f"Parallel Task: Generating {section['title']}")
            ai_draft = call_gemini_sync(prompt)
            
            return section_id, {
                "id": section_id,
                "title": section['title'],
                "aiDraft": ai_draft,
                "userOverride": None,
                "confidence": context.get('confidence', 0.8)
            }

        # --- Parallel Execution ---
        from concurrent.futures import ThreadPoolExecutor
        sections_to_process = config['sections']
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(process_section, sections_to_process))

        # Reconstruct metadata in the exact order defined in config
        results_map = dict(results)
        for s in config['sections']:
            s_id = s['id']
            if s_id == 'metadata':
                metadata['sections'].append({
                    "id": "metadata",
                    "title": "Document Information",
                    "formData": answers
                })
            else:
                metadata['sections'].append(results_map[s_id])

        metadata['status'] = 'draft'
        return metadata

    def parse_unstructured_notes(self, report_type, raw_text):
        """
        Takes raw unstructured text (e.g. from ChatGPT or a meeting transcript),
        and maps it to the schema's dictionary structure using Gemini AI mapping.
        """
        if report_type not in REPORT_TYPES:
            raise ValueError(f"Unknown report type: {report_type}")

        config = REPORT_TYPES[report_type]
        
        # Flatten schema to give Gemini clarity on what answers we need
        questions_schema = {}
        for section in config['sections']:
            for q in section.get('questions', []):
                val_type = q.get('type')
                if val_type == 'dropdown':
                    expected_format = f"Enum: {q.get('options', [])}"
                else:
                    expected_format = val_type
                
                questions_schema[q['id']] = {
                    "question": q['label'],
                    "expected_type": expected_format
                }
                
        # Ask Gemini to extract data strictly into a JSON dictionary
        from agent_manager import call_gemini_sync
        prompt = f"""
        You are an intelligent data extraction tool.
        Your task is to read the raw notes provided below and extract the relevant
        information to answer specific schema questions.

        CRITICAL: 
        1. Try to populate EVERY field in the schema.
        2. If a piece of information is simply NOT FOUND in the raw text, return "*" (an asterisk) for that key. 
        3. Do NOT invent data, but be thorough in mapping synonymous terms.
        4. Do NOT leave fields as empty strings if you can identify them, or if they are missing use "*".
        5. VALUES MUST BE THE ANSWERS THEMSELVES (Strings, Numbers, or Arrays of strings). 
        6. DO NOT return nested JSON objects like {"answer": "...", "question": "..."}. Just return the answer directly as the value for the key.

        SCHEMA TO FILL:
        {json.dumps(questions_schema, indent=2)}

        RAW NOTES (User provided):
        \"\"\"{raw_text}\"\"\"

        Return ONLY a flat JSON dictionary mapping exactly the 'id' from the SCHEMA to the extracted answers. 
        Example: {{"prepared_by": "John Doe", "sprint_number": 4}}
        """
        
        logger.info(f"Extracting structured answers for {report_type} via Auto-Fill feature.")
        generated_json_text = call_gemini_sync(prompt)
        
        try:
            # Clean up the response in case Gemini added markdown fences
            clean_text = generated_json_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            result_dict = json.loads(clean_text.strip())
            
            # Sanitize any textual outputs in the auto-fill too
            for k, v in result_dict.items():
                if isinstance(v, str):
                    result_dict[k] = self._sanitize_markdown(v)
                    
            return result_dict
        except Exception as e:
            logger.error(f"Failed to parse Auto-Fill JSON: {e} \nRaw output: {generated_json_text}")
            raise ValueError("Failed to parse AI structured response.")

    def refine_section(self, report_type, section_id, action, current_text, answers):
        """
        Specialized AI Co-pilot for section refinement.
        """
        if report_type not in REPORT_TYPES or action not in REPORT_TYPES[report_type]["transformations"]:
            raise ValueError(f"Invalid report type {report_type} or action {action}")

        # Calculate section index starting with 1 at the Introduction
        config = REPORT_TYPES[report_type]
        transformation_instr = config["transformations"][action]
        section_meta = next((s for s in config["sections"] if s["id"] == section_id), None)
        if not section_meta:
            raise ValueError(f"Section {section_id} not found in report type {report_type}")

        section_index = config['sections'].index(section_meta)
        
        # Retrieve context again (or we could pass it from frontend)
        context = self.retrieve_filtered_context(section_meta.get('retrieval_query', section_id), doc_type="guideline")

        prompt = f"""
        You are an expert McKinsey-style editor working on an Adept report.
        
        Current Section: {section_id}
        Action Requested: {action.upper()} - {transformation_instr}
        
        --- BASE GUIDELINES ---
        {context['text']}
        
        --- CURRENT TEXT ---
        {current_text}
        
        --- TASK ---
        Apply the requested action to the text while strictly adhering to Adept's professional tone. 
        1. Preserve all key data points.
        2. Ensure sub-section numbering is maintained: {section_index}.1, {section_index}.2, etc.
        3. NEVER use bullet points (*) for major sub-headings. ALWAYS use the {section_index}.X format.
        4. Maintain double-newlines between topics for clarity.
        5. If the original text contains placeholders like [mention features] and you still have no data, replace them with 'N/A'.
        6. Do NOT include the main section title ({section_meta['title']}) in your response.
        """
        
        from agent_manager import call_gemini_sync
        refined_text = call_gemini_sync(prompt)
        return self._sanitize_markdown(refined_text)

    def analyze_report(self, report_type, sections):
        """
        The 'Advisor' layer: Checks for inconsistencies and risks.
        """
        # Collapse sections for analysis
        report_text = json.dumps(sections, indent=2)
        
        prompt = f"""
        Analyze the following report data for a {report_type}.
        Identify:
        1. INCONSISTENCIES: (e.g. status is 'On Track' but issues list is long and critical).
        2. RISKS: Potential project risks mentioned or implied.
        3. SUGGESTIONS: How to make this report more impactful.
        
        REPORT DATA:
        {report_text}
        
        Return ONLY a JSON object with keys: "inconsistencies", "risks", "suggestions".
        Each key must be a list of objects: {{"text": "the observation", "target_id": "the section id it relates to"}}.
        The 'target_id' MUST match one of the keys in the REPORT DATA provided.
        """
        
        from agent_manager import call_gemini_sync
        analysis_json = call_gemini_sync(prompt)
        try:
            # Simple extraction of JSON from response
            import re
            match = re.search(r'\{.*\}', analysis_json, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except:
            pass
        return {"inconsistencies": [], "risks": [], "suggestions": []}

    def retrieve_filtered_context(self, query, doc_type=None, section_name=None):
        """
        High-Precision Retrieval + Confidence Calculation.
        """
        context_parts = []
        max_score = 0
        
        must_filters = []
        if doc_type:
            must_filters.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))
        if section_name:
            must_filters.append(FieldCondition(key="section_name", match=MatchValue(value=section_name)))
        query_filter = Filter(must=must_filters) if must_filters else None

        try:
            from agent_manager import get_embeddings_model
            model = get_embeddings_model()
            vector = model.encode(query).tolist()
            
            results = self.qdrant.search(
                collection_name="adept_database",
                query_vector=vector,
                query_filter=query_filter,
                limit=5
            )
            
            for res in results:
                max_score = max(max_score, res.score)
                context_parts.append(f"[Context | {res.payload.get('source')}] {res.payload.get('text')}")
        except Exception as e:
            logger.warning(f"Qdrant retrieval failed: {e}")

        # Map score to Interpretable Confidence
        level = "Low"
        reason = "Limited matching guidelines found for this section."
        if max_score > 0.8:
            level = "High"
            reason = "Strict alignment with Adept Delivery Playbook & Standards."
        elif max_score > 0.6:
            level = "Med"
            reason = "Moderate match with organizational templates."
            
        return {
            "text": "\n\n".join(context_parts),
            "confidence": {"level": level, "reason": reason}
        }

    def export_to_docx(self, report_type, section_list, output_path, report_title=""):
        """
        Fills a DOCX template using docxtpl.
        Matches the complex dictionary-based expectations of the Word templates.
        """
        config = REPORT_TYPES[report_type]
        template_path = config['docx_template']
        if not os.path.exists(template_path):
            logger.warning(f"Template not found at {template_path}.")
            return False

        # 1. Transform list back to dictionary for template direct-lookups with numbering
        sections_dict = {}
        for i, s in enumerate(section_list):
            s_copy = s.copy()
            # Prefix title with number (Start from 2 since Introduction/Header is 1)
            s_copy['title'] = f"{i + 2}. {s['title']}"
            sections_dict[s['id']] = s_copy
        
        # 2. Extract cover page metadata (usually from 'metadata' section)
        metadata_sec = sections_dict.get('metadata', {})
        form_data = metadata_sec.get('formData', {})
        
        # 3. Build the context matching word/document.xml tags
        rich_context = {
            "currentDate": datetime.now().strftime("%d %B %Y").upper(),
            "title": report_title or config['title'],
            "sections": sections_dict
        }
        
        # Sprinkle in flat metadata fields for easy access (e.g. {{ project_name }})
        rich_context.update(form_data)

        try:
            doc = DocxTemplate(template_path)
            doc.render(rich_context)

            # Force Word to update fields (like TOC) on open
            element = doc.settings.element.find(qn('w:updateFields'))
            if element is None:
                element = OxmlElement('w:updateFields')
                element.set(qn('w:val'), 'true')
                doc.settings.element.append(element)
            else:
                element.set(qn('w:val'), 'true')

            # --- Footer Suppression for Cover Page ---
            # Word documents are split into sections. Usually, the cover is in the first section.
            if doc.sections:
                first_section = doc.sections[0]
                first_section.different_first_page_header_footer = True
                # Clear footer for the first page if it exists
                first_section.footer.is_linked_to_previous = False
                for p in first_section.footer.paragraphs:
                    p.text = ""

            doc.save(output_path)
            return True
        except Exception as e:
            logger.error(f"Docx render error: {e}")
            raise e

    def _formdata_to_markdown(self, form_data, section_config=None):
        """
        Converts a formData dictionary into readable Markdown text.
        Uses the section schema to get human-readable labels.
        """
        if not form_data:
            return ""
        
        # Build a label lookup from the schema if available
        label_map = {}
        if section_config:
            for q in section_config.get('questions', []):
                label_map[q['id']] = q['label']
        
        lines = []
        for key, value in form_data.items():
            if not value:
                continue
            label = label_map.get(key, key.replace('_', ' ').title())
            val_str = str(value).strip()
            if not val_str:
                continue
            
            # Multi-line values (lists, textareas) — render as sub-content
            if '\n' in val_str:
                lines.append(f"**{label}:**")
                for line in val_str.split('\n'):
                    line = line.strip()
                    if line:
                        # Preserve existing bullet formatting, otherwise add one
                        if line.startswith(('-', '*', '•', '✅', '⏳')):
                            lines.append(line)
                        else:
                            lines.append(f"- {line}")
            else:
                lines.append(f"**{label}:** {val_str}")
        
        return "\n".join(lines)

    def export_to_markdown(self, report_type, section_list, report_title=""):
        """
        Collapses the report into a single high-fidelity Markdown document.
        Falls back to formData when no AI draft exists.
        """
        config = REPORT_TYPES[report_type]
        title = report_title or config['title']
        
        # Build a section config lookup for label resolution
        section_configs = {s['id']: s for s in config.get('sections', [])}
        
        md_lines = [
            f"# {title.upper()}",
            f"**Date:** {datetime.now().strftime('%d %B %Y')}",
            "",
            "---",
            ""
        ]
        
        for i, s in enumerate(section_list):
            if s.get('id') == 'metadata':
                continue
                
            md_lines.append(f"## {i}. {s.get('title', 'Untitled')}")
            
            # Priority: userOverride → aiDraft → formData → N/A
            content = s.get('userOverride') or s.get('aiDraft') or ''
            if not content or not content.strip():
                form_data = s.get('formData', {})
                sec_config = section_configs.get(s.get('id'))
                content = self._formdata_to_markdown(form_data, sec_config)
            
            md_lines.append(content if content.strip() else "N/A")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
            
        return "\n".join(md_lines)

# Singleton instance
engine = ReportAutomationEngine()
