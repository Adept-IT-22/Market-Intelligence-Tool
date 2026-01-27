#!/bin/bash
# Batch Ingest Directory Script
# This script ingests all supported files from a directory into the Market Intelligence database

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
INPUT_DIR=""
SECTORS="Innovations,Product Development"
SUMMARY="Adept Technologies Innovation Projects"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --input)
            INPUT_DIR="$2"
            shift 2
            ;;
        --sectors)
            SECTORS="$2"
            shift 2
            ;;
        --summary)
            SUMMARY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --input <directory> [--sectors <sectors>] [--summary <summary>]"
            exit 1
            ;;
    esac
done

if [ -z "$INPUT_DIR" ]; then
    echo "Error: --input directory is required"
    echo "Usage: $0 --input <directory> [--sectors <sectors>] [--summary <summary>]"
    exit 1
fi

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Directory not found: $INPUT_DIR"
    exit 1
fi

echo "========================================"
echo "Market Intelligence - Batch Ingestion"
echo "========================================"
echo "Input Directory: $INPUT_DIR"
echo "Sectors: $SECTORS"
echo "Summary: $SUMMARY"
echo "========================================"
echo ""

# Activate virtual environment if it exists
if [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
    echo "✓ Virtual environment activated"
elif [ -d "$SCRIPT_DIR/../venv" ]; then
    source "$SCRIPT_DIR/../venv/bin/activate"
    echo "✓ Virtual environment activated"
fi

# Run the ingest script
python "$SCRIPT_DIR/ingest_data.py" \
    --input "$INPUT_DIR" \
    --sectors "$SECTORS" \
    --summary "$SUMMARY"

echo ""
echo "========================================"
echo "Ingestion completed!"
echo "========================================"
