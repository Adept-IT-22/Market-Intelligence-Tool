import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import sys
import os
from unittest.mock import MagicMock

# Mock dependencies that might be missing locally
sys.modules["qdrant_client"] = MagicMock()
sys.modules["qdrant_client.models"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["fastapi"] = MagicMock()
sys.modules["google.auth"] = MagicMock()
sys.modules["google.auth.transport.requests"] = MagicMock()
sys.modules["dotenv"] = MagicMock()

# Adjust path to import agent_manager
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent_manager import _call_gemini_api_internal, logger

class TestGeminiRetry(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        # Patch dependencies that are outside the function scope or hard to mock directly in usage
        self.token_patcher = patch('agent_manager.get_access_token', return_value="fake_token")
        self.mock_get_token = self.token_patcher.start()
        
        # Suppress logging during tests
        logger.disabled = True

    async def asyncTearDown(self):
        self.token_patcher.stop()
        logger.disabled = False

    @patch("httpx.AsyncClient")
    async def test_success_first_try(self, mock_client_cls):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Success"}]}}]
        }
        
        # Setup mock client
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        result = await _call_gemini_api_internal("test prompt")
        self.assertEqual(result, "Success")
        self.assertEqual(mock_client_instance.post.call_count, 1)

    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_success(self, mock_sleep, mock_client_cls):
        # Setup failure response then success response
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.json.return_value = {}
        fail_response.text = "Service Unavailable"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Success after retry"}]}}]
        }

        mock_client_instance = AsyncMock()
        # side_effect iterates through the list for each call
        mock_client_instance.post.side_effect = [fail_response, success_response]
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        result = await _call_gemini_api_internal("test prompt")
        self.assertEqual(result, "Success after retry")
        self.assertEqual(mock_client_instance.post.call_count, 2)
        mock_sleep.assert_called_once() # Should sleep once

    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_max_retries_exceeded(self, mock_sleep, mock_client_cls):
        # Setup persistent failure
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.json.return_value = {}
        fail_response.text = "Service Unavailable"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = fail_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        # Should raise RuntimeError (wrapped from the 503) after 5 attempts
        with self.assertRaises(RuntimeError) as cm:
            await _call_gemini_api_internal("test prompt")
        
        self.assertIn("Gemini API Error 503", str(cm.exception))
        self.assertEqual(mock_client_instance.post.call_count, 5)

    @patch("httpx.AsyncClient")
    async def test_non_retryable_error_400(self, mock_client_cls):
        # Setup 400 response (client error, should not retry)
        fail_response = MagicMock()
        fail_response.status_code = 400
        fail_response.json.return_value = {"error": "Bad Request"}
        fail_response.text = "Bad Request"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = fail_response
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        with self.assertRaises(ValueError) as cm:
            await _call_gemini_api_internal("test prompt")
        
        self.assertIn("Gemini API Client Error 400", str(cm.exception))
        self.assertEqual(mock_client_instance.post.call_count, 1) # Should fail immediately

    @patch("httpx.AsyncClient")
    async def test_cancellation(self, mock_client_cls):
        # Simulate CancelledError during request
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = asyncio.CancelledError("Cancelled")
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_cls.return_value = mock_client_instance

        with self.assertRaises(asyncio.CancelledError):
            await _call_gemini_api_internal("test prompt")
        
        # Should NOT retry on cancellation
        self.assertEqual(mock_client_instance.post.call_count, 1)

if __name__ == '__main__':
    unittest.main()
