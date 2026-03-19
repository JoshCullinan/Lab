from contextlib import contextmanager
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from core.results import PatientResult, TestResult


console = Console(force_terminal=True)


class ResultsDisplay:
    def __init__(self, con: Optional[Console] = None):
        self._con = con or console

    # ── Patient header ────────────────────────────────────────────────────────

    def show_patient_header(self, result: PatientResult) -> None:
        lines = [
            f"[bold]Patient:[/bold]     {result.patient_name}",
            f"[bold]DOB:[/bold]         {result.dob}",
            f"[bold]MRN:[/bold]         {result.patient_id}",
            f"[bold]Episode:[/bold]     {result.episode}",
            f"[bold]Specimen:[/bold]    {result.specimen_id}",
            f"[bold]Ordered By:[/bold]  {result.requesting_doctor}",
            f"[bold]Status:[/bold]      {result.status}",
            f"[bold]Collected:[/bold]   {result.collection_datetime}",
            f"[bold]Result:[/bold]      {result.result_datetime}",
        ]
        self._con.print(Panel("\n".join(lines), title="Patient Information", expand=False))

    # ── Results table ─────────────────────────────────────────────────────────

    def show_results_table(self, result: PatientResult) -> None:
        if not result.tests:
            self._con.print("[yellow]No test results found for this specimen.[/yellow]")
            return

        table = Table(
            title=f"Results — {result.specimen_id}",
            show_header=True,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Test", style="white", no_wrap=True, ratio=5)
        table.add_column("Value", justify="right", no_wrap=True, ratio=2)
        table.add_column("Unit", style="dim", no_wrap=True, ratio=4)
        table.add_column("Ref Range", style="dim", no_wrap=True, ratio=3)
        table.add_column("Flag", justify="center", no_wrap=True, ratio=1)

        for t in result.tests:
            flag_text = self._format_flag(t.flag)
            value_style = self._value_style(t.flag)
            table.add_row(
                t.test_name,
                Text(t.value, style=value_style),
                t.unit,
                t.reference_range,
                flag_text,
            )

        self._con.print(table)

    # ── Status messages ───────────────────────────────────────────────────────

    def show_scanning_status(self, message: str) -> None:
        self._con.print(f"[cyan]{message}[/cyan]")

    def show_error(self, message: str) -> None:
        self._con.print(f"[bold red]Error:[/bold red] {message}")

    def show_success(self, message: str) -> None:
        self._con.print(f"[bold green]✓[/bold green] {message}")

    def show_info(self, message: str) -> None:
        self._con.print(f"[dim]{message}[/dim]")

    @contextmanager
    def show_spinner(self, message: str):
        """Context manager that shows a spinner while the block runs."""
        with Live(Spinner("line", text=message), console=self._con, refresh_per_second=10):
            yield

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _format_flag(flag: Optional[str]) -> Text:
        if not flag:
            return Text("")
        upper = flag.upper()
        if upper == "CRITICAL":
            return Text("CRITICAL", style="bold red")
        if upper == "PENDING":
            return Text("P", style="dim cyan")
        if upper in ("H", "HIGH"):
            return Text("H", style="yellow")
        if upper in ("L", "LOW"):
            return Text("L", style="yellow")
        return Text(flag)

    @staticmethod
    def _value_style(flag: Optional[str]) -> str:
        if not flag:
            return "white"
        upper = flag.upper()
        if upper == "CRITICAL":
            return "bold red"
        if upper == "PENDING":
            return "dim"
        if upper in ("H", "HIGH", "L", "LOW"):
            return "yellow"
        return "white"
