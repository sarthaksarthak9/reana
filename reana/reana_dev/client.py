# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2020, 2022, 2023, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""`reana-dev`'s command line client commands."""

import base64
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import traceback

import click

from reana.config import CLIENT_FLAVOUR_EXECUTABLES, REPO_LIST_CLIENT
from reana.reana_dev.utils import get_srcdir, run_command


@click.group()
def client_commands():
    """Client commands group."""


def get_scripts_dir():
    """Return the scripts directory of the environment running ``reana-dev``."""
    if sys.prefix == sys.base_prefix:
        click.secho(
            "[ERROR] `reana-dev` is not running inside a virtual environment. "
            "Please activate the `reana` virtual environment first.",
            fg="red",
        )
        sys.exit(1)
    return Path(sysconfig.get_path("scripts"))


def is_component_go_package(component):
    """Return whether the component is a Go package."""
    return os.path.exists(os.path.join(get_srcdir(component), "go.mod"))


def _ensure_client_components_checked_out():
    """Exit if an expected client component is not checked out."""
    for component in REPO_LIST_CLIENT:
        srcdir = get_srcdir(component)
        if not os.path.isdir(srcdir):
            click.secho(
                f"[ERROR] Expected client component '{component}' is not "
                f"checked out at {srcdir}.",
                fg="red",
            )
            sys.exit(1)


def get_missing_go_build_tools():
    """Return unavailable executables required to build the Go client."""
    return [tool for tool in ("go", "make") if not shutil.which(tool)]


def _get_python_client_components():
    """Return checked-out client components containing Python packages."""
    components = []
    for component in REPO_LIST_CLIENT:
        srcdir = get_srcdir(component)
        if os.path.exists(os.path.join(srcdir, "setup.py")) or os.path.exists(
            os.path.join(srcdir, "pyproject.toml")
        ):
            components.append(component)
    return components


def _install_go_clients(scripts_dir):
    """Install checked-out Go clients into the current scripts directory."""
    for component in REPO_LIST_CLIENT:
        if is_component_go_package(component):
            missing_tools = get_missing_go_build_tools()
            if missing_tools:
                click.secho(
                    "[WARNING] Skipping Go client installation because these "
                    f"build tools were not found: {', '.join(missing_tools)}. "
                    "Install them and rerun `reana-dev client-install`.",
                    fg="yellow",
                )
                return
            executable = scripts_dir / CLIENT_FLAVOUR_EXECUTABLES["go"]
            run_command(
                ["make", "install", f"BINDIR={scripts_dir}"],
                component,
            )
            run_command([str(executable), "version"], component)


@client_commands.command(name="client-install")
def client_install():  # noqa: D301
    """Install latest REANA command line clients and their dependencies.

    Python components are installed in a single pip invocation so that
    pip can resolve version constraints from all local source
    directories together, avoiding conflicts when local branches
    have different dependency pins than published PyPI versions. The Go
    client is built into the current virtual environment's scripts directory
    when Go and make are available; otherwise its installation is skipped
    with a warning.
    """
    scripts_dir = get_scripts_dir()
    _ensure_client_components_checked_out()

    paths = [get_srcdir(component) for component in _get_python_client_components()]
    if paths:
        run_command(
            [sys.executable, "-m", "pip", "install", "--upgrade", *paths],
            "reana",
        )
    run_command([sys.executable, "-m", "pip", "check"], "reana")
    _install_go_clients(scripts_dir)


@client_commands.command(name="client-uninstall")
def client_uninstall():  # noqa: D301
    """Uninstall REANA command line clients and their dependencies.

    Go client removal is skipped with a warning if make is unavailable.
    """
    scripts_dir = get_scripts_dir()
    _ensure_client_components_checked_out()

    python_components = _get_python_client_components()
    if python_components:
        run_command(
            [sys.executable, "-m", "pip", "uninstall", "-y", *python_components],
            "reana",
        )
    run_command([sys.executable, "-m", "pip", "check"], "reana")

    for component in REPO_LIST_CLIENT:
        if is_component_go_package(component):
            if not shutil.which("make"):
                click.secho(
                    "[WARNING] Skipping Go client removal because `make` was "
                    "not found. Any installed Go client binary remains. "
                    "Install make and rerun `reana-dev client-uninstall`.",
                    fg="yellow",
                )
                return
            run_command(
                ["make", "uninstall", f"BINDIR={scripts_dir}"],
                component,
            )


@client_commands.command(name="client-setup-environment")
@click.option("--server-hostname", help="Set customized REANA Server hostname.")
@click.option("--insecure-url", is_flag=True, help="REANA Server URL with HTTP.")
@click.option(
    "--namespace", "-n", default="default", help="Kubernetes namespace [default]"
)
@click.option("--instance-name", default="reana", help="REANA instance name")
def client_setup_environment(
    server_hostname, insecure_url, namespace, instance_name
):  # noqa: D301
    """Display commands to set up shell environment for local cluster.

    Display commands how to set up REANA_SERVER_URL and REANA_ACCESS_TOKEN
    suitable for current local REANA cluster deployment. The output should be
    passed to eval.
    """
    try:
        export_lines = []
        component_export_line = "export {env_var_name}={env_var_value}"
        export_lines.append(
            component_export_line.format(
                env_var_name="REANA_SERVER_URL",
                env_var_value=server_hostname or "https://localhost:30443",
            )
        )
        get_access_token_cmd = [
            "kubectl",
            "get",
            "secret",
            "-n",
            namespace,
            "-o",
            "json",
            f"{instance_name}-admin-access-token",
        ]
        secret_json = json.loads(subprocess.check_output(get_access_token_cmd).decode())
        admin_access_token_b64 = secret_json["data"]["ADMIN_ACCESS_TOKEN"]
        admin_access_token = base64.b64decode(admin_access_token_b64).decode()
        export_lines.append(
            component_export_line.format(
                env_var_name="REANA_ACCESS_TOKEN", env_var_value=admin_access_token
            )
        )

        click.echo("\n".join(export_lines))
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style(
                "Environment variables could not be generated: \n{}".format(str(e)),
                fg="red",
            ),
            err=True,
        )


client_commands_list = list(client_commands.commands.values())
