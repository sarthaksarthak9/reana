# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Tests for reana-dev release-* commands."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from reana.config import (
    GITHUB_RELEASE_TITLE_COMPONENT_NAMES,
    REPO_LIST_CLIENT,
    REPO_LIST_CLUSTER,
)
from reana.reana_dev.cli import reana_dev


@pytest.mark.parametrize(
    "component, tag, expected_title",
    [
        ("reana", "0.9.4", "0.9.4"),
        ("reana", "v0.6.1", "0.6.1"),
        ("reana-client", "0.9.6", "REANA-Client 0.9.6"),
        ("reana-db", "0.9.5", "REANA-DB 0.9.5"),
        ("reana-ui", "0.9.4", "REANA-UI 0.9.4"),
        ("reana-auth-vomsproxy", "1.3.0", "REANA-Auth-VOMSproxy 1.3.0"),
        (
            "reana-workflow-engine-cwl",
            "0.95.0-alpha.1",
            "REANA-Workflow-Engine-CWL 0.95.0-alpha.1",
        ),
    ],
)
def test_get_expected_github_release_title(component, tag, expected_title):
    """Test the expected GitHub release titles."""
    from reana.reana_dev.release import get_expected_github_release_title

    assert get_expected_github_release_title(component, tag) == expected_title


def test_all_released_components_have_a_title():
    """Test that all cluster and client components have a release title."""
    for component in set(REPO_LIST_CLUSTER + REPO_LIST_CLIENT):
        assert component in GITHUB_RELEASE_TITLE_COMPONENT_NAMES


def _run_release_github_title(args, releases):
    """Run ``release-github-title`` with mocked ``gh`` commands."""
    executed_commands = []

    def mock_run_command(cmd, *args, **kwargs):
        executed_commands.append(cmd)
        if "list" in cmd:
            return json.dumps(releases)
        if "view" in cmd:
            tag = cmd[cmd.index("view") + 1]
            return json.dumps(
                next(release for release in releases if release["tagName"] == tag)
            )
        return ""

    with patch("reana.reana_dev.release.which", return_value="/usr/bin/gh"), patch(
        "reana.reana_dev.release.run_command", side_effect=mock_run_command
    ):
        result = CliRunner().invoke(reana_dev, ["release-github-title"] + args)
    return result, executed_commands


def test_release_github_title_amends_wrong_title():
    """Test that a wrongly titled release is amended."""
    result, executed_commands = _run_release_github_title(
        ["-c", "reana-client"], [{"tagName": "0.9.6", "name": "v0.9.6"}]
    )

    assert result.exit_code == 0
    assert executed_commands[-1] == [
        "gh",
        "release",
        "edit",
        "0.9.6",
        "-R",
        "reanahub/reana-client",
        "--title",
        "REANA-Client 0.9.6",
    ]


def test_release_github_title_keeps_correct_title():
    """Test that a correctly titled release is left alone."""
    result, executed_commands = _run_release_github_title(
        ["-c", "reana-client"], [{"tagName": "0.9.6", "name": "REANA-Client 0.9.6"}]
    )

    assert result.exit_code == 0
    assert not any("edit" in cmd for cmd in executed_commands)
    assert "already titled" in result.output


def test_release_github_title_all_releases():
    """Test that all the past releases are amended."""
    result, executed_commands = _run_release_github_title(
        ["-c", "reana-client", "--all-releases"],
        [
            {"tagName": "0.9.6", "name": "v0.9.6"},
            {"tagName": "0.9.5", "name": "v0.9.5"},
            {"tagName": "0.9.3", "name": "REANA-Client 0.9.3"},
        ],
    )

    assert result.exit_code == 0
    assert "1000" in executed_commands[0]
    edited_tags = [cmd[3] for cmd in executed_commands if "edit" in cmd]
    assert edited_tags == ["0.9.6", "0.9.5"]


def test_release_github_title_given_tag():
    """Test that a given release tag is amended."""
    result, executed_commands = _run_release_github_title(
        ["-c", "reana-client", "--tag", "0.9.5"],
        [
            {"tagName": "0.9.6", "name": "v0.9.6"},
            {"tagName": "0.9.5", "name": "v0.9.5"},
        ],
    )

    assert result.exit_code == 0
    edited_tags = [cmd[3] for cmd in executed_commands if "edit" in cmd]
    assert edited_tags == ["0.9.5"]


def test_release_github_title_dry_run():
    """Test that the dry run mode does not amend anything."""
    executed_commands = []

    def mock_run_command(cmd, *args, **kwargs):
        executed_commands.append((cmd, kwargs.get("dry_run", False)))
        return json.dumps([{"tagName": "0.9.6", "name": "v0.9.6"}])

    with patch("reana.reana_dev.release.which", return_value="/usr/bin/gh"), patch(
        "reana.reana_dev.release.run_command", side_effect=mock_run_command
    ):
        result = CliRunner().invoke(
            reana_dev, ["release-github-title", "-c", "reana-client", "--dry-run"]
        )

    assert result.exit_code == 0
    assert executed_commands[-1][1] is True


def test_release_github_title_tag_and_all_releases_are_exclusive():
    """Test that --tag and --all-releases cannot be used together."""
    result, _ = _run_release_github_title(
        ["-c", "reana-client", "--tag", "0.9.5", "--all-releases"], []
    )

    assert result.exit_code == 1
    assert "either --tag or --all-releases" in result.output


def test_release_github_title_skips_unreleased_components():
    """Test that components without GitHub releases are skipped."""
    result, executed_commands = _run_release_github_title(
        ["-c", "reana-demo-helloworld"], []
    )

    assert result.exit_code == 0
    assert not executed_commands
    assert "not released on GitHub" in result.output


def test_release_github_title_requires_gh():
    """Test that the command fails when GitHub CLI is not installed."""
    with patch("reana.reana_dev.release.which", return_value=None), patch(
        "reana.reana_dev.release.run_command"
    ) as mock_run_command:
        result = CliRunner().invoke(
            reana_dev, ["release-github-title", "-c", "reana-client"]
        )

    assert result.exit_code == 1
    assert "Please install GitHub CLI" in result.output
    mock_run_command.assert_not_called()


def test_release_github_title_tag_with_multiple_components():
    """Test that --tag cannot be used with multiple components."""
    result, executed_commands = _run_release_github_title(
        ["-c", "reana-client", "-c", "reana-db", "--tag", "0.9.5"], []
    )

    assert result.exit_code == 1
    assert "Cannot use --tag with multiple components" in result.output
    assert not executed_commands


def test_release_github_title_no_releases():
    """Test that components without any GitHub releases are skipped."""
    result, executed_commands = _run_release_github_title(
        ["-c", "reana-workflow-validator"], []
    )

    assert result.exit_code == 0
    assert "No GitHub releases found" in result.output
    assert not any("edit" in cmd for cmd in executed_commands)
