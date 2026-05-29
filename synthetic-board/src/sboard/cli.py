"""CLI entry point for sboard.

Thin Typer wrapper over `sboard.service`. The service does the orchestration and
I/O; this module only parses arguments, renders results, and maps failures to
exit codes.
"""

from __future__ import annotations

from pathlib import Path

import typer

from sboard import service

app = typer.Typer(
    name="sboard",
    help="Synthetic Advisory Board — convene meetings, inspect memos, run A/B tests.",
    no_args_is_help=True,
)


@app.command()
def convene(
    petition: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to petition JSON file",
    ),
    db: Path = typer.Option(
        service.DEFAULT_DB_PATH,
        "--db",
        envvar="SBOARD_DB",
        help="Append-only SQLite audit database.",
    ),
    out: Path = typer.Option(
        service.DEFAULT_OUT_DIR,
        "--out",
        envvar="SBOARD_OUT",
        help="Directory where the memo .md/.json are written.",
    ),
    personas: Path = typer.Option(
        service.DEFAULT_PERSONAS_DIR,
        "--personas",
        envvar="SBOARD_PERSONAS",
        help="Directory of persona .md files for the board seats.",
    ),
    seed: int = typer.Option(
        service.DEFAULT_SEED,
        "--seed",
        help="Deterministic seed for anonymization shuffling.",
    ),
    show_memo: bool = typer.Option(
        True,
        "--show-memo/--no-show-memo",
        help="Print the rendered memo to stdout in addition to writing it.",
    ),
) -> None:
    """Run a board meeting on a petition and produce a memo."""
    try:
        result = service.convene(
            petition,
            personas_dir=personas,
            db_path=db,
            out_dir=out,
            seed=seed,
        )
    except service.ConveneError as exc:
        typer.secho(f"Meeting aborted: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if show_memo:
        typer.echo(result.memo_markdown)
        typer.echo("")

    typer.secho(
        f"✓ Verdict: {result.memo.verdict.value.upper()}  "
        f"(memo {result.memo.memo_id})",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"  Memo written to: {result.memo_md_path}")
    typer.echo(f"  Memo JSON:       {result.memo_json_path}")
    typer.echo(
        f"  Audit DB:        {result.db_path}  "
        f"({result.transcript_entries} transcript entries)"
    )
    typer.echo(f"  Inspect with:    sboard inspect {result.memo.memo_id}")


@app.command()
def inspect(
    memo_id: str = typer.Argument(..., help="Memo UUID to inspect"),
    db: Path = typer.Option(
        service.DEFAULT_DB_PATH,
        "--db",
        envvar="SBOARD_DB",
        help="Append-only SQLite audit database to read from.",
    ),
) -> None:
    """Display a memo and its full transcript."""
    inspection = service.load_inspection(memo_id, db_path=db)
    if inspection is None:
        typer.secho(
            f"No memo found with id '{memo_id}' in {db}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(service.render_inspection(inspection))


@app.command()
def ab(petition: str = typer.Argument(..., help="Path to petition JSON file")) -> None:
    """Run board + baseline on the same petition for blind A/B comparison."""
    typer.secho(
        "`sboard ab` arrives in Task 10 (the A/B harness); not implemented yet.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
