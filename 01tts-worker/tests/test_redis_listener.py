import unittest
from unittest.mock import Mock, patch

from worker import TaskWorker


class RedisListenerTest(unittest.TestCase):
    @patch("worker.Path.open")
    @patch("worker.asyncio.run")
    @patch("worker.requests.post")
    @patch("worker.requests.get")
    def test_worker_consumes_and_uploads_task(self, mock_get, mock_post, mock_run, mock_path_open):
        queue = Mock()
        queue.brpop.return_value = ("queue:tts_tasks", b"task-1")
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "prompt": "Explain Threads",
            "voice": "en-US-AvaNeural",
            "difficulty": "medium",
            "sourceType": "TEXT",
        }
        generator = Mock()
        generator.generate_lesson.return_value = {
            "uuid": "task-1",
            "title": "Explain Threads",
            "sourceType": "TEXT",
            "sourceUrl": "",
            "level": "medium",
            "passage": "A thread is a lightweight process.",
            "simplifiedPassage": "A thread is a small process.",
            "audioUrl": "",
            "vocabulary": [],
            "questions": [],
            "speakingPrompts": ["Summarize threads."],
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_run.side_effect = lambda coroutine: coroutine.close()
        mock_path_open.return_value.__enter__.return_value = Mock()

        worker = TaskWorker(queue, generator, "http://server")
        self.assertTrue(worker.run_once())
        mock_post.assert_called()
        mock_run.assert_called_once()

    @patch("worker.requests.get")
    @patch("worker.requests.post")
    def test_worker_notifies_failure_on_exception(self, mock_post, mock_get):
        queue = Mock()
        queue.brpop.return_value = ("queue:tts_tasks", b"task-err")
        mock_get.side_effect = Exception("Server connection error")

        generator = Mock()
        worker = TaskWorker(queue, generator, "http://server")

        with self.assertRaises(Exception):
            worker.run_once()

        # Should attempt to notify fail endpoint
        mock_post.assert_called_with("http://server/api/v1/tasks/task-err/fail", data={"reason": "Server connection error"}, timeout=10)


if __name__ == "__main__":
    unittest.main()
