"""Adapter HTTP regressions using synthetic audio and mocked upstream calls."""
import base64
import io
import math
import shutil
import struct
import subprocess
import wave
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openai_tts_adapter as adapter

class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(adapter.app, raise_server_exceptions=False)
        self.upstream = AsyncMock()
        self.patch = patch.object(adapter, 'client', return_value=self.upstream)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def response(self, **kwargs):
        self.upstream.post.return_value = httpx.Response(
            200, request=httpx.Request('POST', 'http://synthetic/v1/tts'), **kwargs)

    def speech(self, **kwargs):
        return self.client.post('/v1/audio/speech', json={
            'input': 'Synthetic test', 'response_format': 'wav', **kwargs})

    def test_wav_pass_through_and_voice_mapping(self):
        audio = b'RIFF synthetic WAV'
        self.response(json={'audio': base64.b64encode(audio).decode()})
        response = self.speech(voice='alloy')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, audio)
        self.assertEqual(response.headers['content-type'], 'audio/wav')
        self.assertEqual(response.headers['x-miotts-preset'], 'jp_female')
        self.assertEqual(self.upstream.post.call_args.kwargs['json']['reference']['preset_id'], 'jp_female')

    def test_invalid_format_rejected_before_upstream(self):
        response = self.speech(response_format='invalid')
        self.assertEqual(response.status_code, 400)
        self.upstream.post.assert_not_called()

    def test_invalid_json_returns_bad_gateway(self):
        self.response(content=b'not JSON')
        self.assertEqual(self.speech().status_code, 502)

    def test_missing_audio_returns_bad_gateway(self):
        self.response(json={})
        self.assertEqual(self.speech().status_code, 502)

    def test_non_object_response_returns_bad_gateway(self):
        self.response(json=['audio'])
        self.assertEqual(self.speech().status_code, 502)

    def test_invalid_audio_returns_bad_gateway(self):
        for audio in (None, 123, {}, '', '!!!', 'abc', 'YWJj$'):
            with self.subTest(audio=audio):
                self.response(json={'audio': audio})
                with patch.object(adapter, '_transcode') as transcode:
                    self.assertEqual(self.speech().status_code, 502)
                    transcode.assert_not_called()

    def test_upstream_timeout_returns_bad_gateway(self):
        self.upstream.post.side_effect = httpx.ReadTimeout('synthetic timeout')
        self.assertEqual(self.speech().status_code, 502)

    def test_upstream_http_error_preserved(self):
        self.upstream.post.return_value = httpx.Response(
            503, text='synthetic unavailable', request=httpx.Request('POST', 'http://synthetic'))
        self.assertEqual(self.speech().status_code, 503)

    def test_invalid_speed_and_empty_input_do_not_call_upstream(self):
        for kwargs in ({'speed': 0}, {'speed': -1}, {'input': ' '}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.speech(**kwargs).status_code, 400)
        self.upstream.post.assert_not_called()

    def test_output_format_alias(self):
        self.response(json={'audio': 'YWJj'})
        self.assertEqual(self.speech(response_format=None, output_format='WAV').content, b'abc')

class TranscodeTests(unittest.TestCase):
    def test_aac_uses_adts_muxer(self):
        with patch.object(adapter.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b'synthetic aac'
            self.assertEqual(adapter._transcode(b'wav', 'aac', 1), b'synthetic aac')
        self.assertEqual(run.call_args.args[0][-3:], ['-f', 'adts', 'pipe:1'])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg is not on PATH')
    def test_real_audio_conversion(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b''.join(struct.pack('<h', int(4000 * math.sin(2 * math.pi * 440 * i / 16000)))
                                     for i in range(8000)))
        for fmt in ('aac', 'mp3', 'flac', 'opus', 'wav'):
            with self.subTest(format=fmt):
                audio = adapter._transcode(buffer.getvalue(), fmt, 1.25)
                self.assertTrue(audio)
                decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0',
                                          '-f', 'null', '-'], input=audio, capture_output=True)
                self.assertEqual(decoded.returncode, 0, decoded.stderr.decode())

    def test_tempo_chain_supports_extreme_speeds(self):
        for speed in (0.125, 0.5, 1, 2, 8):
            with self.subTest(speed=speed):
                filters = adapter._atempo_filters(speed)
                product = 1.0
                for entry in filters:
                    factor = float(entry.split('=')[1])
                    self.assertTrue(0.5 <= factor <= 2)
                    product *= factor
                self.assertAlmostEqual(product, speed)

if __name__ == '__main__':
    unittest.main()
