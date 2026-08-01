<!-- LabScribe target documentation format (spec §7).
     The synthesis engine (M3) generates content matching this structure.
     Replace with your own template if yours differs. -->

# {{LAB_TITLE}}

> Built and documented in an isolated home lab environment that I own.
> Documentation generated with LabScribe and reviewed by hand.

## 1. Overview

{{ONE_PARAGRAPH_SUMMARY}}

| Host | OS | Role | IP |
|---|---|---|---|
| DC01 | Windows Server 2022 | Domain Controller + DNS | 10.10.10.10 |
| WKS01 | Windows 11 | Domain-joined workstation | 10.10.10.20 |
| SIEM01 | Ubuntu + Splunk | SIEM / log collector | 10.10.10.30 |
| KALI01 | Kali Linux | Attacker box | 10.10.10.40 |

## 2. Network Diagram

```mermaid
{{MERMAID_DIAGRAM}}
```

## 3. Build Steps

<!-- Per machine: what was configured, WHY it matters, screenshot refs -->

## 4. Troubleshooting Log

| Issue | Cause | Fix |
|---|---|---|

## 5. Attack & Detection Scenarios

| Scenario | Attack (KALI01) | Detection (SIEM01) | Status |
|---|---|---|---|

## 6. Lessons Learned

-

## 7. Changelog

<!-- LabScribe appends a dated entry per session -->
