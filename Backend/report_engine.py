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
# from agent_manager import call_gemini_sync # Moved to methods to prevent import stall

logger = logging.getLogger(__name__)

# --- Environment Context ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 7000))
# ES context removed

# --- Report Type Abstraction ---
REPORT_TYPES = {
    "sprint": {
        "title": "Sprint Report",
        "sections": [
            {
                "id": "metadata",
                "title": "Document Information",
                "questions": [
                    {"id": "project_name", "label": "Project Name", "type": "text"},
                    {"id": "report_by", "label": "Prepared By", "type": "text"},
                    {"id": "sprint_no", "label": "Sprint Number", "type": "number"},
                    {"id": "period", "label": "Reporting Date", "type": "date"}
                ]
            },
            {
                "id": "status",
                "title": "Sprint Summary & Health",
                "questions": [
                    {"id": "status_rating", "label": "Overall Status", "type": "dropdown", "options": ["Delayed", "On Track", "Ahead"]},
                    {"id": "summary_text", "label": "High-Level Summary", "type": "textarea"},
                    {"id": "timeline", "label": "Timeline (e.g. 4th - 15th Aug)", "type": "text"},
                    {"id": "time_spent", "label": "Time Spent Total", "type": "text"},
                    {"id": "what_next", "label": "What Next?", "type": "textarea"}
                ],
                "retrieval_query": "how to write executive summary adept status report standards"
            },
            {
                "id": "progress",
                "title": "Detailed Accomplishments",
                "questions": [
                    {"id": "tasks_completed", "label": "What was achieved this sprint?", "type": "list"}
                ],
                "retrieval_query": "adept progress reporting guidelines delivery playbook accomplishments"
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
                "title": "Sprint 4 Priorities",
                "questions": [
                    {"id": "upcoming_tasks", "label": "Immediate Priorities", "type": "list"}
                ],
                "retrieval_query": "adept future planning next steps delivery lifecycle"
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
        # Remove bold markers
        text = text.replace("**", "").replace("__", "")
        # Remove Markdown headers (levels 1-6) only at the start of lines
        text = re.sub(r'^\s*#{1,6}\s+', '', text, flags=re.MULTILINE)
        return text.strip()

    def generate_report_draft(self, report_type, answers):
        """
        Builds the report section-by-section using the Wizard answers.
        Returns a dict of SectionState-like objects.
        """
        if report_type not in REPORT_TYPES:
            raise ValueError(f"Unknown report type: {report_type}")

        config = REPORT_TYPES[report_type]
        final_sections = {}

        for section in config['sections']:
            section_id = section['id']
            if section_id == 'metadata':
                # No generation needed for metadata, just pass through
                # Keep metadata under the section id so the returned dict remains consistently keyed
                metadata_answers = {
                    q['id']: answers.get(q['id'], "")
                    for q in section['questions']
                }
                final_sections[section_id] = {
                    "aiDraft": "",
                    "userOverride": None,
                    "isEdited": False,
                    "confidence": {"level": "High", "reason": "System Generated"},
                    "answers": metadata_answers
                }
                continue

            # Fetch context for this section
            query = section.get('retrieval_query', section['title'])
            # We filter by 'guideline' or 'logic' to get the rules, not just any text.
            context = self.retrieve_filtered_context(query, doc_type="guideline")
            
            # Extract relevant user answers for this section
            section_data = {q['id']: answers.get(q['id']) for q in section['questions']}
            
            # Prompt Gemini
            from agent_manager import call_gemini_sync
            prompt = f"""
            You are the Adept Report Synthesizer.
            Your goal is to transform rough user updates into high-quality professional report content.
            
            --- ADEPT GUIDELINES & STANDARDS ---
            {context['text']}
            
            --- USER UPDATES FOR {section['title'].upper()} ---
            {json.dumps(section_data, indent=2)}
            
            --- TASK ---
            Write the {section['title']} section for the {config['title']}.
            1. Use professional, active voice.
            2. Follow the tone and formatting logic found in the guidelines.
            3. Be concise and actionable.
            4. Do NOT include placeholders; if data is missing, write a polite summary of what we know.
            
            --- CRITICAL FORMATTING RULES ---
            - Absolutely NO Markdown formatting.
            - NO asterisks (**), NO hashtags (#), NO bolding, NO italics.
            - Output ONLY raw, professional paragraph text.
            - Do NOT include the section title.
            - No intros or outros.
            """
            
            logger.info(f"Generating section: {section['title']}")
            generated_text = call_gemini_sync(prompt)
            
            # Sanitize to be 100% sure no markdown leaks through
            clean_text = self._sanitize_markdown(generated_text)
            
            final_sections[section_id] = {
                "aiDraft": clean_text,
                "userOverride": None,
                "isEdited": False,
                "confidence": context['confidence']
            }

        return final_sections

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

        If a piece of information is simply NOT FOUND in the raw text, return an empty string "" for that key. Do not invent data.

        SCHEMA TO FILL:
        {json.dumps(questions_schema, indent=2)}

        RAW NOTES (User provided):
        \"\"\"{raw_text}\"\"\"

        Return ONLY a raw JSON dictionary mapping exactly the keys from the SCHEMA to the extracted answers. No backticks, no markdown, just the JSON string starting with {{ and ending with }}.
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

        transformation_instr = REPORT_TYPES[report_type]["transformations"][action]
        section_meta = next((s for s in REPORT_TYPES[report_type]["sections"] if s["id"] == section_id), None)
        if not section_meta:
            raise ValueError(f"Section {section_id} not found in report type {report_type}")
        
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
        Ensure all key data points from the original text are preserved.
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
        
        Return ONLY a JSON object with keys: "inconsistencies", "risks", "suggestions" (all lists).
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

        # 1. Transform list back to dictionary for template direct-lookups
        sections_dict = {s['id']: s for s in section_list}
        
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
            doc.save(output_path)
            return True
        except Exception as e:
            logger.error(f"Docx render error: {e}")
            raise e

# Singleton instance
engine = ReportAutomationEngine()
