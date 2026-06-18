"""GNAFER CLI.

A Typer-based command-line interface for geocoding, batch processing,
and serving the REST API.
"""

import asyncio
from pathlib import Path

import typer
import uvicorn

from src.config import settings
from src.llm_verifier import LLMVerifier
from src.main import run_batch
from src.trigram_matcher import TrigramAddressMatcher, get_connection_pool, load_street_types

app = typer.Typer(help="GNAFER: High-Performance Australian Geocoder CLI")

_DEFAULT_INPUT = Path("data/input.txt")
_DEFAULT_OUTPUT = Path("data/geocoded.csv")


@app.command()
def geocode(
    address: str = typer.Argument(..., help="Australian address to geocode"),
    llm: bool = typer.Option(False, help="Enable LLM verification for near-matches"),
) -> None:
    """Geocode a single address."""
    abbreviations = load_street_types(settings.psv_path)
    pool = get_connection_pool()
    try:
        matcher = TrigramAddressMatcher(pool=pool, abbreviations=abbreviations)
        result = matcher.match(address)
        if result.similarity_score == 0:
            typer.echo(f"Could not geocode: {address}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Score: {result.similarity_score}")
        typer.echo(f"PID:   {result.address_detail_pid}")
        typer.echo(f"Label: {result.address_label}")
        if llm and settings.llm_verify_threshold <= result.similarity_score < 1.0:
            verifier = LLMVerifier()
            llm_available = asyncio.run(verifier.check_available())
            if llm_available:
                verified = asyncio.run(verifier.verify_async(address, result.address_label))
                if verified:
                    typer.echo("LLM:   VERIFIED (upgraded to 1.0)")
                else:
                    typer.echo("LLM:   REJECTED")
            else:
                typer.echo("LLM:   UNAVAILABLE")
    finally:
        pool.closeall()


@app.command()
def batch(
    input_file: Path = typer.Argument(
        default=_DEFAULT_INPUT,
        help="Path to input file (one address per line)",
    ),
    output_file: Path = typer.Option(
        _DEFAULT_OUTPUT,
        help="Output CSV path",
    ),
    workers: int = typer.Option(
        settings.trigram_workers,
        help="Number of parallel matching workers",
    ),
) -> None:
    """Run batch geocoding from a file."""
    if not input_file.exists():
        typer.echo(f"Input file not found: {input_file}", err=True)
        raise typer.Exit(1)
    asyncio.run(run_batch(input_file=input_file, output_file=output_file, workers=workers))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
) -> None:
    """Launch the FastAPI server."""
    uvicorn.run("src.api:app", host=host, port=port, reload=reload)


def main() -> None:
    app()


if __name__ == "__main__":
    app()
