# Telegram HTTP adapter memory measurement

The Telegram adapter now uses HTTPX directly for getMe/getUpdates/getFile/sendMessage.
The shared pipeline, Discord adapter, naming and batch semantics are retained.
No aiogram import or installation is required.

## Method

Run `scripts/measure_telegram_memory.py` inside a Linux runtime image. It exercises
production `run_bot`, TelegramClient, IngestionPipeline and ImmichClient, replacing
only HTTP transport with deterministic mock responses. Discord modules are also
loaded. The script checks the uploaded JPEG bytes, the success reply and final batch
record. It uses a 200 x 200 JPEG (1,305 bytes), waits one second at idle and after
import, and reports current process RSS from `/proc/self/status`.

```sh
docker build -t immich-chat-importer:http-adapter .
docker run --rm --network none \
  -v "$PWD/scripts/measure_telegram_memory.py:/probe.py:ro" \
  --entrypoint python immich-chat-importer:http-adapter /probe.py
```

## Observed result (2026-11-01)

Final controlled run using the freshly built production image:

| Stage | Current RSS | Time from script start |
| --- | ---: | ---: |
| Both platform modules loaded | 59.34 MiB | 0.614 s |
| Telegram polling and shared clients initialized, idle | 60.14 MiB | 1.624 s |
| One image uploaded and replied | 60.70 MiB | 2.634 s |

The earlier import-only comparison measured about 180 MiB with aiogram loaded.
This is evidence of substantially lower dependency overhead, not a guarantee of
production memory usage or a full equivalence benchmark. No real Telegram/Discord
Gateway or Immich network connection is made. Long-running behavior, large archives
and high message volume require separate observation after deployment. The running
bot was neither restarted nor replaced during this measurement.
