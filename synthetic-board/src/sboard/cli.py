"""CLI entry point for sboard."""

import typer

app = typer.Typer(
    name="sboard",
    help="Synthetic Advisory Board — convene meetings, inspect memos, run A/B tests.",
)


@app.command()
def convene(petition: str = typer.Argument(..., help="Path to petition JSON file")) -> None:
    """Run a board meeting on a petition and produce a memo."""
    typer.echo(f"TODO: convene on {petition}")


@app.command()
def inspect(memo_id: str = typer.Argument(..., help="Memo UUID to inspect")) -> None:
    """Display a memo and its full transcript."""
    typer.echo(f"TODO: inspect {memo_id}")


@app.command()
def ab(petition: str = typer.Argument(..., help="Path to petition JSON file")) -> None:
    """Run board + baseline on the same petition for blind A/B comparison."""
    typer.echo(f"TODO: ab on {petition}")


if __name__ == "__main__":
    app()
