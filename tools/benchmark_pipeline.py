"""Small benchmark utility for crop/caption/finalize throughput."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from core.data.file_handler import load_image_files
from core.pipeline_manager import get_pipeline_manager
from core.telemetry import get_metrics_collector


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Image Cropper Tool pipeline stages.")
    parser.add_argument("--source", required=True, help="Source folder with input images")
    parser.add_argument("--output", required=True, help="Output folder for crops")
    parser.add_argument("--limit", type=int, default=100, help="Max images to process")
    parser.add_argument("--bucket", default="square", choices=["portrait", "square", "landscape"])
    parser.add_argument("--auto-bucket", action="store_true", help="Enable auto bucket selection")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    files = load_image_files(source)[: max(1, args.limit)]
    if not files:
        print("No images found.")
        return

    mgr = get_pipeline_manager()
    start = time.perf_counter()
    outputs = mgr.process_stage2_cropping_batch(
        files,
        output,
        bucket=args.bucket,
        auto_bucket=args.auto_bucket,
        yolo_batch_size=8,
    )
    elapsed = time.perf_counter() - start
    rate = len(outputs) / elapsed if elapsed > 0 else 0.0
    print(f"Cropped {len(outputs)}/{len(files)} images in {elapsed:.2f}s ({rate:.2f} img/s)")
    print("Metrics snapshot:", get_metrics_collector().snapshot())


if __name__ == "__main__":
    main()
