"""
Agent Loop — The reasoning layer for Precision Scout v2.

Transforms simple "Retrieve → Answer" into:
  Plan (decompose) → Retrieve → Think (reflect) → Act (synthesize) → Store (artifact)
"""

import json
import logging
from agent_manager import AgentManager, call_gemini_sync
from workspace_manager import save_artifact, get_project

logger = logging.getLogger(__name__)


class AgentLoop:
    def __init__(self, query, project_id=None, session_id=None, chat_history=None):
        self.query = query
        self.project_id = project_id
        self.session_id = session_id
        self.chat_history = chat_history or []
        
    def run(self):
        """Execute the full agent loop."""
        logger.info(f"=== Starting Agent Loop for '{self.query[:30]}...' ===")
        
        # 1. PLAN
        plan = self._plan()
        logger.info(f"Agent Plan: {len(plan)} steps")
        
        # 2. RETRIEVE & THINK (Iterate over plan)
        step_results = []
        for step in plan:
            logger.info(f"Executing step: {step['task']}")
            
            # Retrieve using existing pipeline
            manager = AgentManager(query=step['task'], chat_history=self.chat_history)
            content = manager.pipeline()
            
            # Think: Reflect on quality
            reflection = self._think(step['task'], content)
            
            step_results.append({
                "task": step["task"],
                "content": content,
                "confidence": reflection["confidence"],
                "sources": reflection["sources"]
            })
            
        # 3. ACT (Synthesize final response)
        final_answer = self._act(step_results)
        
        # 4. STORE
        artifact_file = None
        if self.project_id:
            artifact_file = save_artifact(
                project_id=self.project_id,
                content=final_answer,
                title=self.query[:80],
                artifact_type="analysis",
                query=self.query
            )
            
        # Blend overall confidence
        avg_confidence = sum(s["confidence"] for s in step_results) / len(step_results) if step_results else 0
        all_sources = list(set([src for s in step_results for src in s["sources"]]))
            
        return {
            "answer": final_answer,
            "confidence": avg_confidence,
            "sources": all_sources,
            "artifact": artifact_file,
            "plan_executed": plan
        }
        
    def _plan(self):
        """Decompose query into sub-tasks. Fast path for simple queries."""
        if len(self.query.split()) < 8:
            return [{"task": self.query, "type": "direct"}]
            
        prompt = f"""Decompose the following research query into 2-3 focused sub-tasks.
        Query: "{self.query}"
        
        Return ONLY a JSON array of objects with keys 'task' and 'type' (e.g. 'retrieval', 'comparison').
        Example: [{{"task": "Find total market size", "type": "retrieval"}}]
        """
        try:
            resp = call_gemini_sync(prompt)
            # Find json array in response
            start = resp.find('[')
            end = resp.rfind(']') + 1
            if start != -1 and end != 0:
                return json.loads(resp[start:end])
        except Exception as e:
            logger.warning(f"Planning failed, falling back to direct query: {e}")
            
        return [{"task": self.query, "type": "direct"}]
        
    def _think(self, task, content):
        """Reflect on the quality of retrieved content."""
        # Fast heuristic reflection to avoid extra LLM latency
        confidence = 0.5
        sources = []
        
        # Extract sources from typical AgentManager output format
        import re
        source_matches = re.findall(r'\[(?:Source|File):\s*(.+?)\]', content)
        if source_matches:
            sources = list(set(source_matches))
            confidence += 0.3
            
        if "I could not find" not in content and len(content) > 200:
            confidence += 0.15
            
        return {
            "confidence": min(1.0, confidence),
            "sources": sources
        }
        
    def _act(self, step_results):
        """Synthesize final response from all step results."""
        if len(step_results) == 1:
            return step_results[0]["content"]
            
        synthesize_prompt = "Synthesize the following research findings into a single, cohesive response:\n\n"
        for i, res in enumerate(step_results):
            synthesize_prompt += f"--- Finding {i+1} (from '{res['task']}') ---\n{res['content']}\n\n"
            
        synthesize_prompt += "\nProvide a clear, well-structured final answer."
        return call_gemini_sync(synthesize_prompt)
