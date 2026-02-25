import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import sqlite3
import re
import os

# Set dummy env vars for testing
os.environ["GROQ_API_KEY"] = "test_key"
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_PORT"] = "7000"

from agent_manager import AgentManager

class TestAgentManager(unittest.TestCase):
    @patch('agent_manager.get_embeddings_model')
    @patch('agent_manager.QdrantClient')
    def setUp(self, mock_qdrant, mock_get_embeddings):
        self.mock_embeddings = MagicMock()
        self.mock_embeddings.encode.return_value = [0.1, 0.2, 0.3]
        mock_get_embeddings.return_value = self.mock_embeddings
        
        self.mock_qdrant_client = mock_qdrant.return_value
        
        self.manager = AgentManager(query="test query")

    def test_init_embeddings(self):
        self.assertIsNotNone(self.manager.embeddings)
        self.assertIsNotNone(self.manager.query_vector)

    @patch('agent_manager.sqlite3.connect')
    def test_get_table_schema(self, mock_connect):
        mock_cursor = mock_connect.return_value.cursor.return_value
        mock_cursor.fetchall.return_value = [(0, 'col1', 'TEXT', 0, None, 0)]
        
        schema = self.manager.get_table_schema('sometable')
        
        self.assertEqual(len(schema), 1)
        self.assertEqual(schema[0][1], 'col1')

    def test_search_qdrant(self):
        mock_results = [MagicMock(id=1, payload={'text': 'test'})]
        self.manager.qdrant_client.search.return_value = mock_results
        
        result = self.manager.search_qdrant(top_k=5)
        
        self.assertEqual(result, mock_results)
        self.manager.qdrant_client.search.assert_called()

    @patch('agent_manager.sqlite3.connect')
    @patch('agent_manager.pd.read_sql_query')
    @patch.object(AgentManager, 'search_qdrant')
    @patch('agent_manager.call_gemini_sync')
    def test_get_master_routing_basic(self, mock_gemini, mock_search, mock_read_sql, mock_connect):
        # 1. Mock Semantic Search
        mock_point = MagicMock()
        mock_point.payload = {'routing_table': 'semantic_table'}
        mock_search.return_value = [mock_point]

        # 2. Mock Keyword Search SQL
        df_kw = pd.DataFrame([
            {'table_name': 'kw_table_high', 'score': 2},
            {'table_name': 'kw_table_low', 'score': 1}
        ])
        
        df_master = pd.DataFrame([
            {'id': 1, 'Title': 'Semantic Title', 'Source': 'src', 'Summary': 'sum', 'Datatype': 'dt', 'Sectors': 'sec', 'table_name': 'semantic_table'},
            {'id': 2, 'Title': 'High KW Title', 'Source': 'src', 'Summary': 'sum', 'Datatype': 'dt', 'Sectors': 'sec', 'table_name': 'kw_table_high'},
            {'id': 3, 'Title': 'Low KW Title', 'Source': 'src', 'Summary': 'sum', 'Datatype': 'dt', 'Sectors': 'sec', 'table_name': 'kw_table_low'}
        ])
        
        mock_read_sql.side_effect = [df_kw, df_master]

        # 3. Mock Gemini
        mock_gemini.return_value = "semantic_table"

        # Execute
        result = self.manager.get_master_routing()

        # Verify
        self.assertIn('semantic_table', result)
        self.assertIn('kw_table_high', result)
        self.assertNotIn('kw_table_low', result)

    @patch('agent_manager.sqlite3.connect')
    @patch('agent_manager.pd.read_sql_query')
    @patch.object(AgentManager, 'search_qdrant')
    @patch('agent_manager.call_gemini_sync')
    def test_get_master_routing_fallback(self, mock_gemini, mock_search, mock_read_sql, mock_connect):
        # Mocking LLM failure to trigger fallback
        mock_search.return_value = []
        
        df_kw = pd.DataFrame([{'table_name': 'high1', 'score': 2}])
        df_master = pd.DataFrame([
            {'id': 1, 'Title': 'High Title', 'Source': 'src', 'Summary': 'sum', 'Datatype': 'dt', 'Sectors': 'sec', 'table_name': 'high1'}
        ])
        
        mock_read_sql.side_effect = [df_kw, df_master]

        # Triggering an exception in Gemini call
        mock_gemini.side_effect = Exception("Gemini Timeout")

        # Execute
        result = self.manager.get_master_routing()

        # Verify fallback logic
        self.assertEqual(result, ['high1'])

    @patch('agent_manager.sqlite3.connect')
    @patch('agent_manager.call_gemini_sync')
    def test_get_routing_response(self, mock_gemini, mock_connect):
        # Mock Level 2 Gemini selection
        mock_gemini.return_value = '{"sql_tables": ["t1"], "qdrant_ids": ["q1"]}'
        
        # Mock SQL retrieval for routing table
        mock_read_sql = patch('agent_manager.pd.read_sql_query').start()
        mock_read_sql.return_value = pd.DataFrame([{'id': 1, 'Content': 'some context'}])
        self.addCleanup(patch.stopall)

        result = self.manager.get_routing_response(['table1'])
        
        self.assertEqual(result['sql_tables'], ['t1'])
        self.assertEqual(result['qdrant_ids'], ['q1'])

    @patch('agent_manager.sqlite3.connect')
    @patch('agent_manager.pd.read_sql_query')
    @patch.object(AgentManager, 'search_qdrant')
    def test_get_detail_content(self, mock_search, mock_read_sql, mock_connect):
        # Mock SQL detail
        mock_read_sql.return_value = pd.DataFrame([{'Content': 'sql_detail'}])
        
        # Mock Qdrant detail
        mock_point = MagicMock()
        mock_point.payload = {'text': 'qdrant_detail', 'source': 'src'}
        self.manager.qdrant_client.retrieve.return_value = [mock_point]
        
        selection = {'sql_tables': ['t1'], 'qdrant_ids': ['q1']}
        result = self.manager.get_detail_content(selection)
        
        self.assertIn('sql_detail', result)
        self.assertIn('qdrant_detail', result)

if __name__ == '__main__':
    unittest.main()
