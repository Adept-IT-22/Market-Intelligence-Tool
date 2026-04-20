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
                "title": "Metadata",
                "questions": [
                    {"id": "project_name", "label": "Project Name", "type": "text"},
                    {"id": "sprint_no", "label": "Sprint Number", "type": "number"},
                    {"id": "start_date", "label": "Start Date", "type": "date"},
                    {"id": "end_date", "label": "End Date", "type": "date"}
                ]
            },
            {
                "id": "status",
                "title": "Overall Status",
                "questions": [
                    {"id": "status_rating", "label": "Health", "type": "dropdown", "options": ["On Track", "At Risk", "Delayed"]},
                    {"id": "status_summary", "label": "Executive Summary", "type": "textarea"}
                ],
                "retrieval_query": "how to write executive summary adept status report standards"
            },
            {
                "id": "progress",
                "title": "Accomplishments",
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
                "title": "Priorities for Next Sprint",
                "questions": [
                    {"id": "upcoming_tasks", "label": "Immediate Priorities", "type": "list"}
                ],
                "retrieval_query": "adept future planning next steps delivery lifecycle"
            }
        ],
        "docx_template": "Backend/report_templates/sprint_report.docx",
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
                "title": "Metadata",
                "questions": [
                    {"id": "campaign_name", "label": "Campaign Name", "type": "text"},
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
        "docx_template": "Backend/report_templates/marketing_report.docx",
        "transformations": { "make_executive": "...", "clarify": "...", "shorten": "..." }
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
        "docx_template": "Backend/report_templates/weekly_report.docx",
        "transformations": { "make_executive": "...", "clarify": "...", "shorten": "..." }
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
        "docx_template": "Backend/report_templates/monthly_report.docx",
        "transformations": { "make_executive": "...", "clarify": "...", "shorten": "..." }
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
                for q in section['questions']:
                    final_sections[q['id']] = answers.get(q['id'], "")
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
            
            Output ONLY the section text. No intros or outros.
            """
            
            logger.info(f"Generating section: {section['title']}")
            generated_text = call_gemini_sync(prompt)
            
            final_sections[section_id] = {
                "aiDraft": generated_text,
                "userOverride": None,
                "isEdited": False,
                "confidence": context['confidence']
            }

        return final_sections

    def refine_section(self, report_type, section_id, action, current_text, answers):
        """
        Specialized AI Co-pilot for section refinement.
        """
        if report_type not in REPORT_TYPES or action not in REPORT_TYPES[report_type]["transformations"]:
            raise ValueError(f"Invalid report type {report_type} or action {action}")

        transformation_instr = REPORT_TYPES[report_type]["transformations"][action]
        section_meta = next((s for s in REPORT_TYPES[report_type]["sections"] if s["id"] == section_id), None)
        
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
        return refined_text

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

    def export_to_docx(self, report_type, data, output_path):
        """
        Fills a DOCX template using docxtpl.
        """
        template_path = REPORT_TYPES[report_type]['docx_template']
        if not os.path.exists(template_path):
            # Create a placeholder if it doesn't exist
            logger.warning(f"Template not found at {template_path}. Falling back to basic assembly.")
            return False

        doc = DocxTemplate(template_path)
        doc.render(data)
        doc.save(output_path)
        return True

# Singleton instance
engine = ReportAutomationEngine()
