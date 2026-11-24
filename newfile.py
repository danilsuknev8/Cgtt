import asyncio
import base64
import logging
import os
import re
import tempfile
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("9231872468:AAF5b1EG0ci249DoevIcCJ6P22SwSLh4glU")
MAX_TG_FILE_SIZE = 50 * 1024 * 1024  # Лимит Bot API — 50 МБ

# Не более 2 одновременных скачиваний, чтобы не упереться в 512 МБ RAM на Render Free
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(2)

COOKIE_ENV_MAP = {
    "instagram": ("IyBOZXRzY2FwZSBIVFRQIENvb2tpZSBGaWxlCiMgaHR0cHM6Ly9jdXJsLmhheHguc2UvcmZjL2Nvb2tpZV9zcGVjLmh0bWwKIyBUaGlzIGlzIGEgZ2VuZXJhdGVkIGZpbGUhIERvIG5vdCBlZGl0LgoKLmluc3RhZ3JhbS5jb20JVFJVRQkvCVRSVUUJMTgzMDAxODM4MQljc3JmdG9rZW4JOWVJWVppejBVQWFobEZIanJNU0M4aVM5cmdYdUFleHQKLmluc3RhZ3JhbS5jb20JVFJVRQkvCVRSVUUJMTgzMDAxODE2OAlkYXRyCWQ0UUVhNXJSVnp0YVNJclp1eGhiSTliZAouaW5zdGFncmFtLmNvbQlUUlVFCS8JVFJVRQkxODI2OTk0MTY4CWlnX2RpZAlBRENFNzY5Ny1EODVBLTQyQkQtQjM5Ri00Q0YzMDU2NDAwMzMKLmluc3RhZ3JhbS5jb20JVFJVRQkvCVRSVUUJMTc5NjA2MzE4MQlkcHIJMi44NTcxNDI4NTcxNDI4NTcKLmluc3RhZ3JhbS5jb20JVFJVRQkvCVRSVUUJMTc5NjA2MzIwNwl3ZAkzNzh4NzcxCi5pbnN0YWdyYW0uY29tCVRSVUUJLwlUUlVFCTE4MzAwMTgxNzMJbWlkCWF3U0Vkd0FCQUFGb1ZfUkROODJrRHJXWTJ3anIKLmluc3RhZ3JhbS5jb20JVFJVRQkvCVRSVUUJMTgwMzIzNDM4MQlkc191c2VyX2lkCTQ2MDE3MTE4OTMyCi5pbnN0YWdyYW0uY29tCVRSVUUJLwlUUlVFCTE4MjY5OTQyOTAJc2Vzc2lvbmlkCTQ2MDE3MTE4OTMyJTNBU0ppcTVKWnZiYlVUMnclM0ExOSUzQUFZa3hKa3h1SUg1RnhQek91LTZoXzE5WTJSWlRZOHRZZFZhc01iVlBnQQouaW5zdGFncmFtLmNvbQlUUlVFCS8JVFJVRQkwCXJ1cglHVE4lMkMxNzg0MTQ0NjA0Nzk4MjEzOSUyQzE3OTY2NzAxNjQlM0EwMWZmYjBkYWVmZDE5ZDZhNmFjNTQxODM5NDcwODY1YTVlZTdlNjk1ZmI3YzJlZTZmODBiZThjOTUxOWYxZDdiMTljNjY4MDAK", "/tmp/instagram_cookies.txt"),
    "tiktok": ("IyBOZXRzY2FwZSBIVFRQIENvb2tpZSBGaWxlCiMgaHR0cHM6Ly9jdXJsLmhheHguc2UvcmZjL2Nvb2tpZV9zcGVjLmh0bWwKIyBUaGlzIGlzIGEgZ2VuZXJhdGVkIGZpbGUhIERvIG5vdCBlZGl0LgoKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMAl0dF9jc3JmX3Rva2VuCUUxNXR1VkpULTQ1U0Y3NTdNVlNicDVfVWhERTRYUkppWE1ucwoudGlrdG9rLmNvbQlUUlVFCS8JVFJVRQkxODI2OTk2OTY0CXR0d2lkCTElN0N0Z0ptb0Flb0NXb0pCb0F0RWFnMXZ5MHJVUVRfbm1xU0ZKRTBRaFFnZVpvJTdDMTc5NTQ2MDk2MyU3Qzk5NWExMGUyNzY3N2E5NzgyOTQxZWU3NTQzYTZlYzY4N2IxNDk1YzdjMzRlZWViOWZlNTI3ZGQ4ODA4NzdmNGEKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgxMTAxMjk1OAl0dF9jaGFpbl90b2tlbglManFvL0hDeUUzc2Z6TnQ5TlFYTldBPT0KLnd3dy50aWt0b2suY29tCVRSVUUJLwlUUlVFCTE4MjEzODA5NjIJdGlrdG9rX3dlYmFwcF90aGVtZV9zb3VyY2UJbGlnaHQKLnd3dy50aWt0b2suY29tCVRSVUUJLwlUUlVFCTE4MjEzODA5NjIJdGlrdG9rX3dlYmFwcF90aGVtZQlsaWdodAoudGlrdG9rLmNvbQlUUlVFCS8JVFJVRQkxNzk2MzI0OTY0CW1zVG9rZW4JSkZKZExVLUtLa09Kd1JoNWtaQl9XMjdrUF9lVWphakNiNEszZ0E1MUFhd0llcXg4ZzVhbTlheWwtQldUbGhNbE9keFZWSFNNdVdnWE5mcnRNSEV2OG9fTXlSejZhVW91X1NpLTJYSXQ1c2tDc05rWTB1d2s0UFlvMmNDOGhiSEFaaWxkUEtKbmJHZz0KLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMAlzX3Zfd2ViX2lkCXZlcmlmeV9td3RteGY4b184Mnc5c0tIc19hZGhMXzQ0dXdfOHJnZ192U2Vmb1kyc2t4ZXIKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgwMDY0NDc4NAltdWx0aV9zaWRzCTc3MDY5Nzg0OTM3NDIwNTY0NjElM0FkMjlkMTkxZjQ0YjQ5ZTI5MTE0NTY0NGVlZjkxOTg3OAoudGlrdG9rLmNvbQlUUlVFCS8JVFJVRQkxODAwNjQ0Nzg0CWNtcGxfdG9rZW4JQWdRUUFQTlNGLVJPMHJyS1hyemJJTjAwOFdVVTJGcFB2Nk1hWUtzRERnCi50aWt0b2suY29tCVRSVUUJLwlGQUxTRQkxNzk4MDUyNzg0CXBhc3Nwb3J0X2F1dGhfc3RhdHVzCWYxYjE2YWM2ZjMyMzRjMjFiNzY3NjNkYTYzZTU2MTc1JTJDCi50aWt0b2suY29tCVRSVUUJLwlUUlVFCTE3OTgwNTI3ODQJcGFzc3BvcnRfYXV0aF9zdGF0dXNfc3MJZjFiMTZhYzZmMzIzNGMyMWI3Njc2M2RhNjNlNTYxNzUlMkMKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgyNjU2NDc4NAlzaWRfZ3VhcmQJZDI5ZDE5MWY0NGI0OWUyOTExNDU2NDRlZWY5MTk4NzglN0MxNzk1NDYwNzgyJTdDMTU1NTIwMDAlN0NTYXQlMkMrMjItTWF5LTIwMjcrMTklM0EwNiUzQTIyK0dNVAoudGlrdG9rLmNvbQlUUlVFCS8JVFJVRQkxODExMDEyNzg0CXVpZF90dAliMzRiNjYyOTAzNzk0NzM1MDBmN2I2MWEyNTBiYWQ5YzU3MzcyODc2Yjc1ODRkNmM5NDdhN2UwYzAzMjZjMzZiCi50aWt0b2suY29tCVRSVUUJLwlUUlVFCTE4MTEwMTI3ODQJdWlkX3R0X3NzCWIzNGI2NjI5MDM3OTQ3MzUwMGY3YjYxYTI1MGJhZDljNTczNzI4NzZiNzU4NGQ2Yzk0N2E3ZTBjMDMyNmMzNmIKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgxMTAxMjc4NAlzaWRfdHQJZDI5ZDE5MWY0NGI0OWUyOTExNDU2NDRlZWY5MTk4NzgKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgxMTAxMjc4NAlzZXNzaW9uaWQJZDI5ZDE5MWY0NGI0OWUyOTExNDU2NDRlZWY5MTk4NzgKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgxMTAxMjc4NAlzZXNzaW9uaWRfc3MJZDI5ZDE5MWY0NGI0OWUyOTExNDU2NDRlZWY5MTk4NzgKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgxMTAxMjc4NAl0dF9zZXNzaW9uX3RsYl90YWcJc3R0dCU3QzUlN0MwcDBaSDBTMG5pa1JSV1JPNzVHWWVQX19fX19fX19fcU9hSmd5NnpqV18yblR6eEdMejRPcUxRVEZjYlJSQXJwVXlxX3VDLVJZZEklM0QKLnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTgxMTAxMjc4NAlzaWRfdWNwX3YxCTEuMC4xLUtHTXpNemM1T0RNd01tWXdZVFkxT0dNeFlUSTBNakF3TWpWak5tVTVNbUU1T1RjMU4yUmtZelVLR1FpTmlNaVl0WU9zLW1vUXJwMlMyQVlZc3dzNENFQVNTQVFRQkJvSGRYTmxZWE4wTlNJZ1pESTVaREU1TVdZME5HSTBPV1V5T1RFeE5EVTJORFJsWldZNU1UazROemd5VGdvZ1hTdGNpaUJiZkltNWk5d0tBVDVidDBGREIzeFVRVFdleVktZU9kTHdMYWdTSUcyR0dRc3RSbDlKd3lhR3AwVnp0WkI3bVBwam96QjlXSkotd2VXMFhSLTdHQU1pQm5ScGEzUnZhdwoudGlrdG9rLmNvbQlUUlVFCS8JVFJVRQkxODExMDEyNzg0CXNzaWRfdWNwX3YxCTEuMC4xLUtHTXpNemM1T0RNd01tWXdZVFkxT0dNeFlUSTBNakF3TWpWak5tVTVNbUU1T1RjMU4yUmtZelVLR1FpTmlNaVl0WU9zLW1vUXJwMlMyQVlZc3dzNENFQVNTQVFRQkJvSGRYTmxZWE4wTlNJZ1pESTVaREU1TVdZME5HSTBPV1V5T1RFeE5EVTJORFJsWldZNU1UazROemd5VGdvZ1hTdGNpaUJiZkltNWk5d0tBVDVidDBGREIzeFVRVFdleVktZU9kTHdMYWdTSUcyR0dRc3RSbDlKd3lhR3AwVnp0WkI3bVBwam96QjlXSkotd2VXMFhSLTdHQU1pQm5ScGEzUnZhdwoudGlrdG9rLmNvbQlUUlVFCS8JRkFMU0UJMTgxMTAxMjc4MglzdG9yZS1pZGMJdXNlYXN0NQoudGlrdG9rLmNvbQlUUlVFCS8JRkFMU0UJMTgxMTAxMjc4MglzdG9yZS1jb3VudHJ5LXNpZ24JTUVJRURDSU5WSVBMb3FhZmdhRzFUUVFncXItbGd3MWFsRllLMVVFOE5iUVNjRFk5RTJ6bDFrOHJkdDRna3BuU3R5WUVFQ3hYSHVyQkZSVXRVLVpRYmFMM0ZOZwoudGlrdG9rLmNvbQlUUlVFCS8JRkFMU0UJMTgxMTAxMjc4MglzdG9yZS1jb3VudHJ5LWNvZGUJdXMKLnRpa3Rvay5jb20JVFJVRQkvCUZBTFNFCTE4MTEwMTI3ODIJc3RvcmUtY291bnRyeS1jb2RlLXNyYwl1aWQKLnRpa3Rvay5jb20JVFJVRQkvCUZBTFNFCTE4MTEwMTI3ODIJdHQtdGFyZ2V0LWlkYwl1c2Vhc3Q1Ci50aWt0b2suY29tCVRSVUUJLwlGQUxTRQkxODI2OTk2ODk0CXR0LXRhcmdldC1pZGMtc2lnbgllTnJDT1JGazE1WUw1WE94VVJxVE5UUHgxcVNud3BKT2lYYVVTWmRQVVU2TlB2LU5PYkwxR2xqYVFSd1hpekNHMkhMNEUzbUxPMmRsdkZ2cFRkQzBYUm94LTU5TXJxNHVKZ1YyMk5DVHlsR2JERFRPWkl0a0s1b1ZwZEtTdWJoQXZrN1NGMDE4cUJYaXl0WlpoZm5IbXdaNEJjQmE2aW5DWVB0LTVrekdXY2JBYWZ0SV95NW9NYjFFclpJVlFlRlNfa1JweW1sMEhiQ0RzWGVrYnRvWERwcGJMaGRHYmhBWVZVQ1Z6UEEyZWtNallRSV90eHhWVWswMkM1blJxNnpRTlAyVjZPTy05NXAyT2E5eDNUVjNCV3NaRjlQLW8zclVqaldQOC1hcGpWQzNkS0FVN3JQcmhfaTNzaDR3ZUo0ZTFlUkhTUlZKS2hjcWVueXRwUklkdHlhYm80TmRvcEdnMElQQzVKOW5wT1lGZ25TVmdIdXhSRzUyemRJcUtLWHAwQTdsNXdyZlZoZUJDYW1wNmFZSHhYU0tFbVAzV2NxcFM1dlJ1NlZrQWFjcElBOVZVWU5RQ19Rd251MnZpdzN5WTBfV0pBMFR4RzNPdWZ2eURzVVF6ZjJneER5UFpXVmlEYUtRbGNUYm9aU2EwOVJlTmh0Q2RjQ3F1S2xBa09jNQp3d3cudGlrdG9rLmNvbQlGQUxTRQkvCUZBTFNFCTE4MDMyMzY3ODQJbGFzdF9sb2dpbl9tZXRob2QJZ29vZ2xlCi50aWt0b2suY29tCVRSVUUJLwlGQUxTRQkxODI2OTk2OTY0CW9kaW5fdHQJOGQyYWQ5YTIwNmU0NmEyY2U1NWM0MTE2MDE0MTRiNjI0Y2VjZTViNWJmZGUyY2Y3ZDcyZTQ4Yjk2YmE2OTYzNmZkNzNmZWJjMDdiZmZhNzBlNDMwNzcyNzBhYmUwYWQ5ZTA3NThmOTg4NjY2YmFjOWY5NTVkYzYxZDYzN2IxMjdmNDkyMjcwYWRlMGIxNjEzYWJlZTBlNTdjZDRiMWJlNwoud3d3LnRpa3Rvay5jb20JVFJVRQkvCVRSVUUJMTc5NTg5Mjk2NQlwZXJmX2ZlZWRfY2FjaGUJeyUyMmV4cGlyZVRpbWVzdGFtcCUyMjoxNzk2MDY1MjAwMDAwJTJDJTIyaXRlbUlkcyUyMjpbJTIyNzY4OTExNjc3MzMyNDU0MTIxNCUyMiUyQyUyMjc2OTc2NjU0ODk4NjE5NzEyMTQlMjJdfQoudGlrdG9rLmNvbQlUUlVFCS8JVFJVRQkxODI5MTU2OTY4CWNvb2tpZS1jb25zZW50CXslMjJvcHRpb25hbCUyMjp0cnVlJTJDJTIyZ2ElMjI6dHJ1ZSUyQyUyMmFmJTIyOnRydWUlMkMlMjJmYnAlMjI6dHJ1ZSUyQyUyMmxpcCUyMjp0cnVlJTJDJTIyYmluZyUyMjp0cnVlJTJDJTIydHRhZHMlMjI6dHJ1ZSUyQyUyMnJlZGRpdCUyMjp0cnVlJTJDJTIyaHVic3BvdCUyMjp0cnVlJTJDJTIydmVyc2lvbiUyMjolMjJ2MTAlMjJ9Cnd3dy50aWt0b2suY29tCUZBTFNFCS8JRkFMU0UJMTgwMzIzNjk3MQltc1Rva2VuCXlXNGdGWG81WVpIaENWMUdmTG5QQUxDOV9GdGRodFRrZHBkbnB6enBmSzVsVndDeDFQYngzY2R1bTNNa1B0bTRodkp5Q1dzSk1WbUlZZW5aUlMweEo4YXA2dkszY2xjWGg5RmduYlBzV25USnZuTHBQdGFsem5nWjlCZllHc1Z3VEl0aUUydWFZZ21pYmZxZGhyMFMK", "/tmp/tiktok_cookies.txt"),
    "youtube": ("IyBOZXRzY2FwZSBIVFRQIENvb2tpZSBGaWxlCiMgaHR0cHM6Ly9jdXJsLmhheHguc2UvcmZjL2Nvb2tpZV9zcGVjLmh0bWwKIyBUaGlzIGlzIGEgZ2VuZXJhdGVkIGZpbGUhIERvIG5vdCBlZGl0LgoKLnlvdXR1YmUuY29tCVRSVUUJLwlUUlVFCTE4Mjk1ODg1MDgJX19TZWN1cmUtWUVOSUQJQ3Y0QkNBWVNzQUVCdDdta05nZXZjUmUtUTZhQmR5UG1zSHNjSVQ4d1NFT1VRZTJIbmFudXMyOG1Ya3VMUGxpcUR3MS02bkl1UjhUVnhadjdJRmgzVGtlSjlRSHQ5M0dwYnlYRHloZjNpWVM1OFo5cDVmMmsxS2lyLUpKTXFSQUJ1UDh5NkVrb3B0MzlaUnFPVnMzbV9jY19tb1M5M3RBMzNqa3ppd1VlRHdJTDlCalRPdmZrTWNoeVpsM2xzNFlpU1RNU29Cc3hpamtqN1hMRDJsemhIeFB4bGsxZ3ppbVNXWUxDZTQyODJjNzhoTjdZVUpQenFDZ0dNa1VCZG5MRUdTT2NOOEVvS3Z2MGV1YXNsWmNLUExmTFNSX2hGVEszQkVqSkxuaFE1anM1U28tNkk0WmF5UXlVWFFRWlhyWU9QR0hDUDVYQWZSdkZjN1BRVnFnUmVnSQoueW91dHViZS5jb20JVFJVRQkvCVRSVUUJMAlZU0MJN2pJNEJ4TjhGWTAKLnlvdXR1YmUuY29tCVRSVUUJLwlUUlVFCTE4Mjk1ODg1MDkJX19TZWN1cmUtWUVDCUNndFZhbU16VERJeGVESnVaeWkwbTVMWUJqSUtDZ0pIUWhJRUdnQWdVMkxhQWdyWEFrTjJORUpEUVZsVGMwRkZRblEzYld0T1oyVjJZMUpsTFZFMllVSmtlVkJ0YzBoelkwbFVPSGRUUlU5VlVXVXlTRzVoYm5Wek1qaHRXR3QxVEZCc2FYRkVkekV0Tm01SmRWSTRWRlo0V25ZM1NVWm9NMVJyWlVvNVVVaDBPVE5IY0dKNVdFUjVhR1l6YVZsVE5UaGFPWEExWmpKck1VdHBjaTFLU2sxeFVrRkNkVkE0ZVRaRmEyOXdkRE01V2xKeFQxWnpNMjFmWTJOZmJXOVRPVE4wUVRNemFtdDZhWGRWWlVSM1NVdzVRbXBVVDNabWEwMWphSGxhYkROc2N6UlphVk5VVFZOdlFuTjRhV3ByYWpkWVRFUXliSHBvU0hoUWVHeHJNV2Q2YVcxVFYxbE1RMlUwTWpneVl6YzRhRTQzV1ZWS1VIcHhRMmRIVFd0VlFtUnVURVZIVTA5alRqaEZiMHQyZGpCbGRXRnpiRnBqUzFCTVpreFRVbDlvUmxSTE0wSkZha3BNYm1oUk5XcHpOVk52TFRaSk5GcGhlVkY1VlZoUlVWcFljbGxQVUVkSVExQTFXRUZtVW5aR1l6ZFFVVlp4WjFKbFowayUzRAoueW91dHViZS5jb20JVFJVRQkvCVRSVUUJMTgyOTU4ODUzMglWSVNJVE9SX1BSSVZBQ1lfTUVUQURBVEEJQ2dKSFFoSUVHZ0FnVXclM0QlM0QKLnlvdXR1YmUuY29tCVRSVUUJLwlUUlVFCTE4MzAwMjA1MzMJUFJFRglmNj00MDAwMDAwMCZ0ej1FdXJvcGUuTW9zY293Ci55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxODI2OTk2NTI5CV9fU2VjdXJlLTFQU0lEVFMJc2lkdHMtQ2pRQm5KWnphaExNVE5VWk9RUzMyQjNSZUNGVnFlcWpvN3hmQ0FzVm1GMjZnaDNxSk1iMFhHYlNiVEV1MmlHTmlfcDc3aXJpRUFBCi55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxODI2OTk2NTI5CV9fU2VjdXJlLTNQU0lEVFMJc2lkdHMtQ2pRQm5KWnphaExNVE5VWk9RUzMyQjNSZUNGVnFlcWpvN3hmQ0FzVm1GMjZnaDNxSk1iMFhHYlNiVEV1MmlHTmlfcDc3aXJpRUFBCi55b3V0dWJlLmNvbQlUUlVFCS8JRkFMU0UJMTgzMDAyMDUyOQlIU0lECUFFbE4tWFVkekdvbmFTMm1zCi55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxODMwMDIwNTI5CVNTSUQJQXd4WFltZk11aDFPbTlyMkkKLnlvdXR1YmUuY29tCVRSVUUJLwlGQUxTRQkxODMwMDIwNTI5CUFQSVNJRAlxODBnOGV5MGd2R1BOSjc2L0FOVDZaWTZxVlR5bUtaWWlPCi55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxODMwMDIwNTI5CVNBUElTSUQJbVk1VWU3U1R6VHduTFhSVy9BNGFNVnlPcXJ4T20xbjRWWAoueW91dHViZS5jb20JVFJVRQkvCVRSVUUJMTgzMDAyMDUyOQlfX1NlY3VyZS0xUEFQSVNJRAltWTVVZTdTVHpUd25MWFJXL0E0YU1WeU9xcnhPbTFuNFZYCi55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxODMwMDIwNTI5CV9fU2VjdXJlLTNQQVBJU0lECW1ZNVVlN1NUelR3bkxYUlcvQTRhTVZ5T3FyeE9tMW40VlgKLnlvdXR1YmUuY29tCVRSVUUJLwlGQUxTRQkxODMwMDIwNTI5CVNJRAlnLmEwMDBGQW00Z0JPMlZobVZnNTV3bHZSQ3JYSjZ2OXRiWU9Kd1RfeWV1UlprNEhzSnd2S0ZFQW9tendicGFlZGhld2RRVDUzaGdBQUNnWUtBVTBTQVJZU0ZRSEdYMk1pLXZrU0pZLS1vQ09pa0cyU1pjTks4aG9WQVVGOHlLb2pPWllnQzc2clJWLV9nN3RRQ0lWRzAwNzYKLnlvdXR1YmUuY29tCVRSVUUJLwlUUlVFCTE4MzAwMjA1MjkJX19TZWN1cmUtMVBTSUQJZy5hMDAwRkFtNGdCTzJWaG1WZzU1d2x2UkNyWEo2djl0YllPSndUX3lldVJaazRIc0p3dktGUkQ0d0liZ3VwRVhLYWg3cjJPSmp1UUFDZ1lLQVdvU0FSWVNGUUhHWDJNaTNiZTYtZERSbFg2cEFoLXZ2bWRBdFJvVkFVRjh5S3BnQ1RqRGE4WFg4VkdpYV90eHZINlMwMDc2Ci55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxODMwMDIwNTI5CV9fU2VjdXJlLTNQU0lECWcuYTAwMEZBbTRnQk8yVmhtVmc1NXdsdlJDclhKNnY5dGJZT0p3VF95ZXVSWms0SHNKd3ZLRjRnQzlWSFpUSTBPRERvY2Y0NFVFNlFBQ2dZS0FTd1NBUllTRlFIR1gyTWl0WUtxY19McHlQckJKdVJ3N243QWl4b1ZBVUY4eUtvalU1TGpZN1VSOXgteEJqT0c4WHM0MDA3NgoueW91dHViZS5jb20JVFJVRQkvCUZBTFNFCTE4MjY5OTY1MzQJU0lEQ0MJQVBEX1NLRTZOQzgxb3QxQ2RNNi0wclFZSjVyUEpSYnJrLTJjY1loZW9vUlhrMGE0RGg4WmJBTTVMS19yOWpaMlVGUUgxNjVLCi55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxODI2OTk2NTM0CV9fU2VjdXJlLTFQU0lEQ0MJQVBEX1NLRzVLYVVMSzNoQXltMzV4Y05kSGtaSWRweHZaU19LbGtlTHlNbFhZWHJxTl9teTY3ZnFNS1p1OEVJZFRwaWh2VXg4amcKLnlvdXR1YmUuY29tCVRSVUUJLwlUUlVFCTE4MjY5OTY1MzQJX19TZWN1cmUtM1BTSURDQwlBUERfU0tGSmRRTVlnQ3A4aFFkVjh0aEhwdTJNRXAteHNIaDdKN3FCcEVFWk50QWswbEdxRmp4cVRKcmJra3QxOHlQVkJwMmMKLnlvdXR1YmUuY29tCVRSVUUJLwlUUlVFCTE4MzAwMjA1MzIJTE9HSU5fSU5GTwlBRm1tRjJzd1JRSWhBSl9GOU94Z1hucURNSmZzOEJTQVV3OHVjOHo0djAwem5QbE5jekI2a2NWMUFpQlBHNEcyb3RTTXc1VlZqbW9xMVE2YVdJekdTZnZHcFRpMTRqbkxWOTNoY2c6UVVRM01qTm1lR0ppUjNCUFRERmtUamRPU21wMFNYWjJhbkJPTTJkaldHTmhPWGxRVEZkaUxYcDNYMVY1UVhka2NqUjZSVTFpZFU1VFNYSnBaRzB0VEhKaE1HSkxlblZNTUdONWRraFRXVzVLUmxWV1RISkNRVzl4VDFseGRIQk1PVzlOV1VkYVlVaFdUMEZ2Vm5WUFdXZDVjazkzUVhkTGRtMW1jVVZpVFVwc04yVjBOSGR6VEVZeE0zWjRiVUZoYWtaamFuTldTak16VXpCUlJtaHFla1pCCi55b3V0dWJlLmNvbQlUUlVFCS8JVFJVRQkxNzk1NDYwNjUyCVlUU0VTU0lPTi1qbnVmZHcJQU5QejlLaHMzR1VJRWFlZC8ycUdqNHdXcUVjZTI3OTh5R1BDclQxQi9JMExXZ2pLRG1yb1hnQnd5V1RHNGd3S1dLWlBaWjVCYnA3c3p1N0lyS0RNOVRKNStyMm5ZN0o3VVRLRStoRVU4WkJ4OWpsak0vU2Y1US9oUUJ0b2RqSGw0ckg3alRHdE1qQTAKLnlvdXR1YmUuY29tCVRSVUUJLwlUUlVFCTE3OTU0NjIzMzIJR1BTCTEK", "/tmp/youtube_cookies.txt"),
}

PLATFORM_NAMES = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube Shorts",
}

PLATFORM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "instagram",
        re.compile(
            r"https?://(?:www\.|m\.)?(?:instagram\.com|instagr\.am)/"
            r"(?:[\w.-]+/)?(?:reel|reels|p|tv|share)/[\w/-]+[^\s]*",
            re.IGNORECASE,
        ),
    ),
    (
        "tiktok",
        re.compile(
            r"https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+",
            re.IGNORECASE,
        ),
    ),
    (
        "youtube",
        re.compile(
            r"https?://(?:www\.|m\.)?youtube\.com/shorts/[\w-]+[^\s]*",
            re.IGNORECASE,
        ),
    ),
]

dp = Dispatcher()


def setup_cookies() -> dict[str, str]:
    """Декодирует cookies из переменных окружения для всех заданных платформ."""
    loaded: dict[str, str] = {}
    for platform, (env_name, file_path) in COOKIE_ENV_MAP.items():
        b64_data = os.getenv(env_name, "").strip()
        if not b64_data:
            continue
        try:
            Path(file_path).write_bytes(base64.b64decode(b64_data))
            loaded[platform] = file_path
            logger.info("Cookies для %s загружены.", platform)
        except Exception as exc:
            logger.error("Не удалось декодировать %s: %s", env_name, exc)
    return loaded


def detect_source(text: str) -> tuple[str, str] | None:
    """Определяет платформу и извлекает очищенную ссылку из текста сообщения."""
    for platform, pattern in PLATFORM_PATTERNS:
        match = pattern.search(text)
        if match:
            url = match.group(0).rstrip(".,)!?\"'>")
            return platform, url
    return None


def build_ydl_opts(platform: str, tmpdir: str, cookiefile: str | None) -> dict:
    """Формирует оптимальные параметры yt-dlp под конкретную платформу."""
    opts: dict = {
        "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        # H.264 + MP4 гарантирует корректное воспроизведение в Telegram на iOS и Android
        "format_sort": ["vcodec:h264", "res:1080", "ext:mp4:m4a"],
    }

    if platform == "tiktok":
        # Единый поток "b" у TikTok берет оригинальный файл воспроизведения без водяного знака
        opts["format"] = "b[ext=mp4]/bv*[ext=mp4]+ba[ext=m4a]/b"
    elif platform == "youtube":
        opts["format"] = "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/bv*+ba/b"
    else:
        opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
        opts["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        }

    if cookiefile and os.path.exists(cookiefile):
        opts["cookiefile"] = cookiefile

    return opts


def download_video(platform: str, url: str, tmpdir: str, cookiefile: str | None) -> dict:
    """Синхронное скачивание через yt-dlp (выполняется в отдельном потоке)."""
    ydl_opts = build_ydl_opts(platform, tmpdir, cookiefile)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("Не удалось получить данные о видео.")

        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        filepath = None
        if info.get("requested_downloads"):
            filepath = info["requested_downloads"][0].get("filepath")

        if not filepath or not os.path.exists(filepath):
            files = sorted(Path(tmpdir).glob("*"), key=lambda p: p.stat().st_size, reverse=True)
            if not files:
                raise RuntimeError("Файл видео не найден после загрузки.")
            filepath = str(files[0])

        return {
            "filepath": filepath,
            "width": info.get("width"),
            "height": info.get("height"),
            "duration": int(info["duration"]) if info.get("duration") else None,
        }


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Отправь ссылку на видео из:\n"
        "• Instagram (Reels / посты)\n"
        "• TikTok (без водяного знака)\n"
        "• YouTube Shorts"
    )


@dp.message(F.text)
async def handle_video_link(message: Message) -> None:
    detected = detect_source(message.text or "")
    if not detected:
        await message.answer(
            "Пришли ссылку на видео из Instagram, TikTok или YouTube Shorts."
        )
        return

    platform, url = detected
    platform_label = PLATFORM_NAMES[platform]

    if platform == "tiktok" and "/photo/" in url.lower():
        await message.answer(
            "Похоже, это фото-слайдшоу TikTok, а не видео — бот скачивает только видеоролики."
        )
        return

    status_msg = await message.answer(f"⏳ Скачиваю видео из {platform_label}...")
    cookie_path = COOKIE_ENV_MAP[platform][1]
    cookiefile = cookie_path if os.path.exists(cookie_path) else None

    try:
        async with DOWNLOAD_SEMAPHORE:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await asyncio.to_thread(
                    download_video, platform, url, tmpdir, cookiefile
                )
                file_size = os.path.getsize(result["filepath"])

                if file_size > MAX_TG_FILE_SIZE:
                    size_mb = file_size / (1024 * 1024)
                    await status_msg.edit_text(
                        f"Видео весит {size_mb:.1f} МБ — Telegram позволяет ботам отправлять файлы до 50 МБ."
                    )
                    return

                await status_msg.edit_text("📤 Отправляю в Telegram...")
                await message.answer_video(
                    video=FSInputFile(result["filepath"]),
                    width=result["width"],
                    height=result["height"],
                    duration=result["duration"],
                    supports_streaming=True,
                )
                await status_msg.delete()

    except yt_dlp.utils.DownloadError as exc:
        logger.warning("Ошибка yt-dlp (%s) для %s: %s", platform, url, exc)
        await status_msg.edit_text(
            f"Не удалось скачать видео из {platform_label}. "
            "Проверь, что ролик публичный и ссылка ведет именно на видео."
        )
    except Exception as exc:
        logger.exception("Непредвиденная ошибка (%s): %s", platform, exc)
        await status_msg.edit_text("Произошла ошибка при обработке видео. Попробуй позже.")


async def start_health_server() -> web.AppRunner:
    """HTTP-сервер для health-check и поддержания активности на Render."""
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="OK"))
    app.router.add_get("/health", lambda _: web.Response(text="OK"))

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health-сервер запущен на порту %s", port)
    return runner


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана.")

    setup_cookies()
    runner = await start_health_server()
    bot = Bot(token=BOT_TOKEN)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
