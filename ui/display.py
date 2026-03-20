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

        # Separate culture reports from regular test rows
        culture_reports = [t for t in result.tests if t.test_name == "Culture Report"]
        regular_tests = [t for t in result.tests if t.test_name != "Culture Report"]

        if regular_tests:
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

            for t in regular_tests:
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

        # Render culture reports as panels below the table
        for cr in culture_reports:
            self._con.print(Panel(
                cr.value, title="Culture Report", border_style="cyan", expand=True,
            ))

    # ── Patient list (name search) ────────────────────────────────────────────

    def show_patient_list(self, hits: list[dict]) -> None:
        """Display a numbered list of patient search results for selection."""
        if not hits:
            self._con.print("[yellow]No patients found.[/yellow]")
            return

        table = Table(
            title="Patient Search Results",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", justify="right", style="dim", no_wrap=True)
        table.add_column("MRN", no_wrap=True)
        table.add_column("Surname", no_wrap=True)
        table.add_column("Given Name", no_wrap=True)
        table.add_column("DOB", no_wrap=True)
        table.add_column("Episode", no_wrap=True)

        for h in hits:
            table.add_row(
                str(h["row_index"] + 1),
                h.get("mrn", ""),
                h.get("surname", ""),
                h.get("given_name", ""),
                h.get("dob", ""),
                h.get("episode", ""),
            )

        self._con.print(table)

    # ── Episode list (hospital MRN search) ──────────────────────────────────

    def show_episode_list(self, episode_data: dict) -> None:
        """Display patient info and a numbered list of episodes for selection."""
        patient_name = episode_data.get("patient_name", "")
        patient_id = episode_data.get("patient_id", "")
        dob = episode_data.get("dob", "")

        header = (
            f"[bold]Patient:[/bold] {patient_name}  "
            f"[bold]MRN:[/bold] {patient_id}  "
            f"[bold]DOB:[/bold] {dob}"
        )
        self._con.print(Panel(header, title="Patient", expand=False))

        rows = episode_data.get("rows", [])
        if not rows:
            self._con.print("[yellow]No episodes found.[/yellow]")
            return

        table = Table(
            title="Lab Episodes",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", justify="right", style="dim", no_wrap=True)
        table.add_column("Episode", no_wrap=True)
        table.add_column("Doctor", no_wrap=True)
        table.add_column("Collected", no_wrap=True)
        table.add_column("Test Sets", ratio=3)

        for i, row in enumerate(rows):
            test_names = ", ".join(c["text"] for c in row.get("clickable", []))
            table.add_row(
                str(i + 1),
                row.get("episode_number", ""),
                row.get("doctor", ""),
                row.get("collection_datetime", ""),
                test_names or "[dim]--[/dim]",
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
