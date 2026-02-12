import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import sys
import os

class TestGeminiRetry(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        # Add local directory to path for import, but track it for cleanup
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        if self.project_root not in sys.path:
            sys.path.insert(0, self.project_root)
            self.path_added = True
        else:
            self.path_added = False

        # Patch environment variables BEFORE importing agent_manager
        self.patcher_env = patch.dict(os.environ, {
            "GCP_PROJECT_ID": "test-project", 
            "GEMINI_API_KEY": "test-key"
        })
        self.patcher_env.start()

        # Create mocks for all dependencies
        self.mock_qdrant = MagicMock()
        self.mock_sentences = MagicMock()
        self.mock_fastapi = MagicMock()
        self.mock_google_auth = MagicMock()
        self.mock_dotenv = MagicMock()
        
        # Setup the patcher for sys.modules
        self.modules_patcher = patch.dict(sys.modules, {
            "qdrant_client": self.mock_qdrant,
            "qdrant_client.models": MagicMock(),
            "sentence_transformers": self.mock_sentences,
            "fastapi": self.mock_fastapi,
            "google.auth": self.mock_google_auth,
            "google.auth.transport.requests": MagicMock(),
            "dotenv": self.mock_dotenv,
        })
        self.modules_patcher.start()

        # Ensure we re-import agent_manager to pick up the mocks and env vars
        if 'agent_manager' in sys.modules:
            del sys.modules['agent_manager']
            
        import agent_manager
        self.agent_manager = agent_manager
        self.logger = agent_manager.logger
        
        # Patch get_access_token separately since it's usage inside the function
        self.token_patcher = patch('agent_manager.get_access_token', return_value="fake_token")
        self.mock_get_token = self.token_patcher.start()
        
        # Suppress logging
        self.logger.disabled = True

    async def asyncTearDown(self):
        self.token_patcher.stop()
        self.modules_patcher.stop()
        self.patcher_env.stop()
        self.logger.disabled = False
        
        # Clean up sys.path if we added it
        if self.path_added:
            if self.project_root in sys.path:
                sys.path.remove(self.project_root)
        
        # CRITICAL: Remove the mocked agent_manager from sys.modules
        if 'agent_manager' in sys.modules:
            del sys.modules['agent_manager']

    @patch("httpx.AsyncClient")
    async def test_success_first_try(self, mock_client_cls):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Success"}]}}]
        }
        
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        # Call the function from the imported module
        result = await self.agent_manager._call_gemini_api_internal("test prompt")
        self.assertEqual(result, "Success")
        self.assertEqual(mock_client_instance.post.call_count, 1)

    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_success(self, mock_sleep, mock_client_cls):
        # Setup failure then success
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.json.return_value = {}
        fail_response.text = "Service Unavailable"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Retry Success"}]}}]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = [fail_response, success_response]
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        result = await self.agent_manager._call_gemini_api_internal("test prompt")
        self.assertEqual(result, "Retry Success")
        self.assertEqual(mock_client_instance.post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_max_retries_exceeded(self, mock_sleep, mock_client_cls):
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.json.return_value = {}
        fail_response.text = "Service Unavailable"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = fail_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        with self.assertRaises(RuntimeError) as cm:
            await self.agent_manager._call_gemini_api_internal("test prompt")
        
        self.assertIn("Max Retries Exceeded", str(cm.exception))
        self.assertEqual(mock_client_instance.post.call_count, 5)

    @patch("httpx.AsyncClient")
    async def test_non_retryable_error_400(self, mock_client_cls):
        fail_response = MagicMock()
        fail_response.status_code = 400
        fail_response.json.return_value = {"error": "Bad Request"}
        fail_response.text = "Bad Request"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = fail_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        with self.assertRaises(ValueError) as cm:
            await self.agent_manager._call_gemini_api_internal("test prompt")
        
        self.assertIn("Gemini API Client Error 400", str(cm.exception))
        self.assertEqual(mock_client_instance.post.call_count, 1)

    @patch("httpx.AsyncClient")
    async def test_cancellation(self, mock_client_cls):
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = asyncio.CancelledError("Cancelled")
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        with self.assertRaises(asyncio.CancelledError):
            await self.agent_manager._call_gemini_api_internal("test prompt")
        
        self.assertEqual(mock_client_instance.post.call_count, 1)

if __name__ == '__main__':
    unittest.main()
