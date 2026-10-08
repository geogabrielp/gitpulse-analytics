"""About: brief project description and link to the full README."""

from __future__ import annotations

import streamlit as st

st.subheader(body=":material/folder_code: Project Overview")

st.markdown(
    body="""
    GitPulse Analytics is an **end-to-end data engineering pipeline** that turns
    public GitHub events from [**GH Archive**](https://www.gharchive.org/) into
    actionable insights about developer productivity, project health, and community
    engagement. All served through a sleek, interactive dashboard.

    Behind the scenes, it implements a **Lakehouse architecture** (Bronze → Silver → Gold).
    """
)

st.subheader(body=":material/stacks: Tech Stack")

st.markdown(
    body="""
| Category | Tool | Role |
|---|---|---|
| :material/cloud: Storage | **MinIO** + **Delta Lake** | S3-compatible object store with ACID transactions |
| :material/acute: Orchestration | **Prefect v3** | Workflow orchestration with retries and observability |
| :material/transform: Transform & Query | **Polars** | Lazy, zero-copy, multi-core DataFrames for ETL and analytics |
| :material/verified: Contracts | **Pandera** | Runtime data validation at every layer |
| :material/dashboard: Dashboard | **Streamlit** | Interactive frontend with cached queries |
| :material/package: Deps | **uv** | Fast Python package manager (no pip) |
"""
)

st.markdown(
    body="""
    For a complete walkthrough: including a quick-start guide,
    project structure, and troubleshooting, check out the project's
    [**README**](https://github.com/geogabrielp/gitpulse-analytics#readme).
    """
)

st.divider()

st.subheader(body=":material/function: GitPulse Score Formula")

st.markdown(
    body="""
    A **daily score** (0–100) that captures repository vitality from four weighted
    GitHub event types. The higher the number, the more active the project on that day:
    """
)

# prettier-ignore
st.latex(
    body=r"""
    \text{GitPulseScore}=
    \min\bigl(
        1\cdot N_{\text{Push}} + 5\cdot N_{\text{Pr}} + 3\cdot N_{\text{Issues}} + 2\cdot N_{\text{Star}},\;
        100
    \bigr)
    """
)

st.markdown(body="Where each event type carries a specific **weight**:")

st.markdown(
    body="""
| Event type | Weight |
|---|---|
| **PushEvent** (commits pushed) | $w = 1$ |
| **PullRequestEvent** (PR opened/closed/merged) | $w = 5$ |
| **IssuesEvent** (issue opened/closed) | $w = 3$ |
| **WatchEvent** (repository starred) | $w = 2$ |

The raw weighted sum is capped at 1.0 before scaling to 100, ensuring a
**bounded 0–100 score** regardless of event volume.
"""
)
