# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-27

### Added

- Daily landing files of a fictional shop from Data-Generator v1.7.1 (seed 42): ten CSV files and a manifest per day,
  order status as later events, product records on every change, no truth columns.
- Idempotent loading into DuckDB's raw schema with manifest (row count, SHA-256) and header checks.
- dbt project: staging with cleaning rules, intermediate (people, product versions, order status, recovered
  quantities), core star schema with contracts and SCD2 product versions, marts (daily sales, traffic, cohorts),
  a data quality log with one warning test per rule, 105 data tests and 5 unit tests.
- Grading against the generator's answer key: every injected issue fixed, caught, fixed wrongly or missed, false
  alarms, the clean shop as a control, and facts reconciled with the generator's own tables.
- Daily Airflow 3.4 DAG calling the project's command line; CI runs it for five days and a rerun and compares the
  result with a full load.
- Dash + Mantine app in the portfolio look, README charts, an animated demo and an ERD drawn from the dbt manifest.
- README in English for the public repository.
