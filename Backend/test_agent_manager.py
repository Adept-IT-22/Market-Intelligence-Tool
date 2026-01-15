import unittest
from unittest.mock import patch, MagicMock
from agent_manager import AgentManager


class TestAgentManager(unittest.TestCase):
    def setUp(self):
        patcher_qdrant = patch('agent_manager.QdrantClient', autospec=True)
        self.addCleanup(patcher_qdrant.stop)
        self.mock_qdrant_client_class = patcher_qdrant.start()
        self.mock_qdrant_client = self.mock_qdrant_client_class.return_value
        self.manager = AgentManager(query="test query")

    @patch('agent_manager.SentenceTransformer')
    def test_init_embeddings(self, mock_embed):
        mock_embed.return_value.encode.return_value = [0.1, 0.2, 0.3]
        manager = AgentManager(query="test")
        self.assertIsNotNone(manager.embeddings)
        self.assertIsNotNone(manager.query_vector)

    @patch('agent_manager.sqlite3.connect')
    @patch('agent_manager.pd.read_sql_query')
    def test_get_table_schema(self, mock_read_sql, mock_connect):
        mock_read_sql.return_value.to_dict.return_value = {'col': [1,2]}
        schema = self.manager.get_table_schema('sometable')
        self.assertIn('col', schema)

    def test_get_sql_routing_schemas_empty(self):
        result = self.manager.get_sql_routing_schemas({})
        self.assertEqual(result, {})

    @patch.object(AgentManager, 'get_table_schema')
    def test_get_sql_routing_schemas(self, mock_schema):
        mock_schema.return_value = {'a': 1}
        result = self.manager.get_sql_routing_schemas({'SQL': ['t1']})
        self.assertIn('t1', result)

    def test_get_qdrant_routing_schemas_empty(self):
        result = self.manager.get_qdrant_routing_schemas({})
        self.assertEqual(result, {})

    @patch.object(AgentManager, 'get_table_schema')
    def test_get_qdrant_routing_schemas(self, mock_schema):
        mock_schema.return_value = {'a': 1}
        result = self.manager.get_qdrant_routing_schemas({'Qdrant': ['t1']})
        self.assertIn('t1', result)

    def test_search_qdrant(self):
        self.manager.qdrant_client = MagicMock()
        self.manager.qdrant_client.query_points.return_value = ['result']
        self.manager.query_vector = [0.1, 0.2]
        result = self.manager.search_qdrant(top_k=1)
        self.assertEqual(result, ['result'])

    @patch('agent_manager.sqlite3.connect')
    @patch('agent_manager.pd.read_sql_query')
    def test_open_databases(self, mock_read_sql, mock_connect):
        self.manager.qdrant_client = MagicMock()
        mock_read_sql.return_value = MagicMock()
        self.manager.qdrant_client.query_points.return_value = 'qdrant_result'
        relevant_tables = {'QDrant': ['q1'], 'SQL': ['s1']}
        result = self.manager.open_databases(relevant_tables)
        self.assertIn('q1', result)
        self.assertIn('s1', result)

if __name__ == '__main__':
    unittest.main()
