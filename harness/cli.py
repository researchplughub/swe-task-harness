import os
import sys
import json
import argparse
import logging

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.logging import RichHandler

from harness import verifier
from harness.verifier import VerificationResult

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)

logger = logging.getLogger("swe-harness.cli")

def read_file_or_string(input_val: str) -> str:
    """Reads file content if the input is an existing path; otherwise returns input.

    Args:
        input_val: File path or raw string.

    Returns:
        str: File content or the raw string.
    """
    if os.path.exists(input_val):
        try:
            with open(input_val, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error("Error reading file %s: %s", input_val, e)
            sys.exit(1)
    return input_val

def display_verification_report(report: VerificationResult) -> None:
    """Renders a structured summary of the verification report using Rich.

    Args:
        report: The verification report dataclass instance.
    """
    console.print("\n")
    
    status_text = "[bold green]PASS[/bold green]" if report.success else "[bold red]FAIL[/bold red]"
    console.print(Panel(
        f"Verification Result: {status_text}\n"
        f"Repository: [cyan]{report.repo_url}[/cyan]\n"
        f"Base Commit: [yellow]{report.base_commit[:8]}[/yellow]",
        title="[bold]Verification Details[/bold]",
        expand=False
    ))

    table = Table(title="Execution Checklist", show_header=True, header_style="bold magenta")
    table.add_column("Checkpoint", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    reproduced = "[green]YES[/green]" if report.reproduced else "[red]NO[/red]"
    pre_exit = report.pre_fix_test_summary.exit_code if report.pre_fix_test_summary.exit_code is not None else "N/A"
    table.add_row("Bug Reproduction (Pre-fix tests fail)", reproduced, f"Exit Code: {pre_exit}")

    resolved = "[green]YES[/green]" if report.resolved else "[red]NO[/red]"
    post_exit = report.post_fix_test_summary.exit_code if report.post_fix_test_summary.exit_code is not None else "N/A"
    table.add_row("Fix Validation (Post-fix tests pass)", resolved, f"Exit Code: {post_exit}")
    
    overall = "[green]VERIFIED[/green]" if report.success else "[red]INVALID[/red]"
    table.add_row("Task Validity", overall, "Reproduction and Resolution succeeded")

    console.print(table)

    cov_info = report.fix_coverage
    if cov_info:
        console.print("\n[bold magenta]Code Coverage (Modified Files):[/bold magenta]")
        cov_table = Table(show_header=True, header_style="bold blue")
        cov_table.add_column("File", style="cyan")
        cov_table.add_column("Coverage", justify="right")
        cov_table.add_column("Missing Line Ranges", style="red")

        mod_cov = cov_info.modified_files_coverage
        for filepath, data in mod_cov.items():
            percent = f"{data.percent_covered:.1f}%"
            missing = data.missing_lines
            missing_str = ", ".join(map(str, missing)) if isinstance(missing, list) else str(missing)
            if not missing_str:
                missing_str = "[green]Fully Covered[/green]"
            cov_table.add_row(filepath, percent, missing_str)

        console.print(cov_table)
        console.print(f"Total Test Suite Coverage: [bold cyan]{cov_info.total_coverage_percent:.1f}%[/bold cyan]")
    else:
        console.print("\n[yellow]No coverage data collected.[/yellow]")
    
    if report.error:
        console.print(f"\n[bold red]Error Details:[/bold red] {report.error}")

def main() -> None:
    """Main CLI entrypoint parser."""
    parser = argparse.ArgumentParser(
        description="Automate environment setup, patch verification, and test coverage analysis for Git repositories."
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")

    verify_parser = subparsers.add_parser("verify", help="Verify reproducing tests and code fixes against a baseline commit.")
    verify_parser.add_argument("--repo-url", "-r", required=True, help="Target Git repository clone URL.")
    verify_parser.add_argument("--base-commit", "-b", required=True, help="Git commit hash of baseline state.")
    verify_parser.add_argument("--test-patch", "-t", required=True, help="Path to test patch or raw diff string.")
    verify_parser.add_argument("--fix-patch", "-f", required=True, help="Path to fix patch or raw diff string.")
    verify_parser.add_argument("--test-targets", "-s", nargs="*", help="Specific test files or targets to run.")
    verify_parser.add_argument("--repo-dir", default="./workspace/temp_repo", help="Clone destination directory.")
    verify_parser.add_argument("--env-dir", default="./workspace/temp_venv", help="Virtual environment directory.")
    verify_parser.add_argument("--output", "-o", help="Path to write the report JSON file.")

    args = parser.parse_args()

    if args.command == "verify":
        test_patch_content = read_file_or_string(args.test_patch)
        fix_patch_content = read_file_or_string(args.fix_patch)

        report = verifier.verify_task(
            repo_url=args.repo_url,
            base_commit=args.base_commit,
            test_patch=test_patch_content,
            fix_patch=fix_patch_content,
            repo_dir=args.repo_dir,
            env_dir=args.env_dir,
            test_targets=args.test_targets
        )

        display_verification_report(report)

        if args.output:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
                with open(args.output, "w", encoding="utf-8") as out_f:
                    json.dump(report.to_dict(), out_f, indent=2)
                logger.info("JSON report saved to %s", args.output)
            except Exception as e:
                logger.error("Failed to write JSON output to %s: %s", args.output, e)

        if not report.success:
            sys.exit(1)
        sys.exit(0)

if __name__ == "__main__":
    main()
