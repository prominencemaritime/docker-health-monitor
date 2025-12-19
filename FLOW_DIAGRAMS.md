# Base Alert Flow Diagrams

## src/core/base_alert.py Workflow with Healthcheck Failures

*Shows the complete execution flow of the alert system's run() method, including all success paths (writing OK status) and failure paths (writing ERROR status with exception details)*
```mermaid
flowchart TD
    Start([alert.run<br/>called]) --> Init[Initialize run_time<br/>Log: RUN STARTED]
    
    Init --> TryBlock{Enter<br/>try block}
    
    TryBlock --> Step1[Step 1: Fetch Data<br/>df = self.fetch_data]
    
    Step1 --> FetchError{Fetch<br/>Exception?}
    FetchError -->|Yes| CatchBlock[Jump to except block]
    FetchError -->|No| CheckEmpty1{df.empty?}
    
    CheckEmpty1 -->|Yes| HealthOK1[Write: OK health_status.txt<br/>Return False]
    CheckEmpty1 -->|No| LogFetched[Log: Fetched N records]
    
    LogFetched --> Step2[Step 2: Validate Columns<br/>validate_required_columns]
    
    Step2 --> ValidateError{Validation<br/>Exception?}
    ValidateError -->|Yes| CatchBlock
    ValidateError -->|No| Step3[Step 3: Filter Data<br/>df_filtered = filter_data]
    
    Step3 --> FilterError{Filter<br/>Exception?}
    FilterError -->|Yes| CatchBlock
    FilterError -->|No| CheckEmpty2{df_filtered<br/>empty?}
    
    CheckEmpty2 -->|Yes| HealthOK2[Write: OK health_status.txt<br/>Return False]
    CheckEmpty2 -->|No| LogFiltered[Log: N records after filtering]
    
    LogFiltered --> Step4[Step 4: Filter Unsent<br/>df_unsent = tracker.filter_unsent_events]
    
    Step4 --> TrackerError{Tracker<br/>Exception?}
    TrackerError -->|Yes| CatchBlock
    TrackerError -->|No| CheckEmpty3{df_unsent<br/>empty?}
    
    CheckEmpty3 -->|Yes| HealthOK3[Write: OK health_status.txt<br/>Log: All previously sent<br/>Return False]
    CheckEmpty3 -->|No| LogUnsent[Log: N new records to notify]
    
    LogUnsent --> Step5[Step 5: Route Notifications<br/>jobs = route_notifications]
    
    Step5 --> RouteError{Route<br/>Exception?}
    RouteError -->|Yes| CatchBlock
    RouteError -->|No| LogJobs[Log: Created N notification jobs]
    
    LogJobs --> Step6[Step 6: Send Notifications<br/>success = _send_notifications]
    
    Step6 --> SendLoop[Loop through jobs]
    
    SendLoop --> SendJob[Send job idx/total]
    SendJob --> SendError{Send<br/>Exception?}
    SendError -->|Yes| LogSendFail[Log: Failed to send<br/>Continue to next job]
    SendError -->|No| SendSuccess[Log: Sent successfully<br/>Track sent keys]
    
    LogSendFail --> MoreJobs{More<br/>jobs?}
    SendSuccess --> MoreJobs
    
    MoreJobs -->|Yes| SendLoop
    MoreJobs -->|No| MarkSent[Mark events as sent<br/>tracker.mark_as_sent]
    
    MarkSent --> HealthOK4[Write: OK health_status.txt<br/>Return success]
    
    HealthOK1 --> Finally
    HealthOK2 --> Finally
    HealthOK3 --> Finally
    HealthOK4 --> Finally
    
    CatchBlock --> LogException[Log: exception<br/>with full traceback]
    LogException --> HealthERROR[Write: ERROR health_status.txt<br/>Include error message<br/>Return False]
    
    HealthERROR --> Finally
    
    Finally[Finally Block:<br/>Log: RUN COMPLETE]
    Finally --> End([End])
    
    style HealthOK1 fill:#90EE90
    style HealthOK2 fill:#90EE90
    style HealthOK3 fill:#90EE90
    style HealthOK4 fill:#90EE90
    style HealthERROR fill:#FF6B6B
    style CatchBlock fill:#FFB6C1
    style FetchError fill:#FFE4B5
    style ValidateError fill:#FFE4B5
    style FilterError fill:#FFE4B5
    style TrackerError fill:#FFE4B5
    style RouteError fill:#FFE4B5
    style SendError fill:#FFE4B5
```

## Healthcheck Failure Conditions Diagram

*Shows the healthcheck script's validation logic: file existence → structure validation → structured parsing → status check (OK/ERROR) → timezone-aware age calculation → pass/fail determination*
```mermaid
flowchart TD
    HC([Docker Healthcheck<br/>python3 healthcheck.py]) --> CheckFile{health_status.txt<br/>exists?}
    
    CheckFile -->|No| Fail1[❌ EXIT 1<br/>Health file not found]
    CheckFile -->|Yes| ValidateStruct[Validate file structure<br/>Size, line count]
    
    ValidateStruct --> StructError{Valid<br/>structure?}
    StructError -->|No| Fail2[❌ EXIT 1<br/>Invalid file structure<br/>Empty or malformed]
    StructError -->|Yes| ParseFile[Parse structured format<br/>Line 1: STATUS TIMESTAMP<br/>Line 2: ALERT_TYPE<br/>Line 3: TIMEZONE<br/>Line 4: ERROR_MSG optional]
    
    ParseFile --> ParseError{Can parse<br/>file?}
    ParseError -->|No| Fail3[❌ EXIT 1<br/>Parse failed<br/>Invalid format]
    ParseError -->|Yes| CheckStatus{Status in<br/>Line 1?}
    
    CheckStatus -->|ERROR| Fail4[❌ EXIT 1<br/>Health status is ERROR<br/>Show: ERROR_MSG]
    CheckStatus -->|OK| GetTZ[Get effective timezone<br/>SCHEDULE_TIMES_TIMEZONE<br/>then TIMEZONE then UTC]
    
    GetTZ --> CalcMaxAge[Calculate max_age based on<br/>schedule mode]
    
    CalcMaxAge --> CheckSchedule{Schedule<br/>Mode?}
    
    CheckSchedule -->|FREQUENCY| CalcFreq[max_age = HOURS × 60 + 10]
    CheckSchedule -->|TIMES| CalcTimes[max_age = time_since_last + 10]
    CheckSchedule -->|Neither| CalcDefault[max_age = 70 minutes]
    
    CalcFreq --> ParseTimestamp
    CalcTimes --> ParseTimestamp
    CalcDefault --> ParseTimestamp
    
    ParseTimestamp[Parse ISO timestamp<br/>from Line 1<br/>Timezone-aware]
    
    ParseTimestamp --> TZError{Timestamp<br/>valid?}
    TZError -->|No| Fail5[❌ EXIT 1<br/>Invalid timestamp<br/>Not timezone-aware]
    TZError -->|Yes| CalcAge[Calculate age using<br/>timezone-aware datetime<br/>now minus timestamp]
    
    CalcAge --> CompareAge{file_age ><br/>max_age?}
    
    CompareAge -->|Yes| Fail6[❌ EXIT 1<br/>Health status too old<br/>Show: age slash max_age minutes]
    CompareAge -->|No| Success[✅ EXIT 0<br/>Healthy<br/>status: OK, age: X slash Y min]
    
    style Fail1 fill:#FF6B6B
    style Fail2 fill:#FF6B6B
    style Fail3 fill:#FF6B6B
    style Fail4 fill:#FF6B6B
    style Fail5 fill:#FF6B6B
    style Fail6 fill:#FF6B6B
    style Success fill:#90EE90
```

## Conditions That Cause Healthcheck Failure

*Maps the four healthcheck failure reasons (file missing, unreadable, ERROR status, too old) to their root causes in the alert application and infrastructure*
```mermaid
flowchart LR
    subgraph Reasons[Healthcheck FAILS When]
        R1[File Missing<br/>app logs health_status.txt<br/>does not exist]
        R2[File Unreadable<br/>Permission error or<br/>I/O error]
        R3[Status = ERROR<br/>File starts with ERROR<br/>not OK]
        R4[File Too Old<br/>Modified time exceeds<br/>schedule plus 10 min buffer]
    end
    
    subgraph Causes[What Causes These]
        C1[App never ran<br/>Container just started]
        C2[App crashed before<br/>writing health file]
        C3[Exception in run<br/>method caught by<br/>except block]
        C4[Scheduler not running<br/>Cron or APScheduler failed<br/>Schedule misconfigured]
    end
    
    subgraph AppStates[base_alert.py States]
        S1[fetch_data exception]
        S2[validate_required_columns<br/>exception]
        S3[filter_data exception]
        S4[tracker exception]
        S5[route_notifications exception]
        S6[send_notifications exception]
        S7[Database connection failed]
        S8[SMTP connection failed]
        S9[Missing required columns]
    end
    
    R1 --> C1
    R1 --> C2
    R2 --> C2
    R3 --> C3
    R4 --> C4
    
    C3 --> S1
    C3 --> S2
    C3 --> S3
    C3 --> S4
    C3 --> S5
    C3 --> S6
    C3 --> S7
    C3 --> S8
    C3 --> S9
    
    style R1 fill:#FF6B6B
    style R2 fill:#FF6B6B
    style R3 fill:#FF6B6B
    style R4 fill:#FF6B6B
    style C3 fill:#FFB6C1
    style S1 fill:#FFE4B5
    style S2 fill:#FFE4B5
    style S3 fill:#FFE4B5
    style S4 fill:#FFE4B5
    style S5 fill:#FFE4B5
    style S6 fill:#FFE4B5
    style S7 fill:#FFE4B5
    style S8 fill:#FFE4B5
    style S9 fill:#FFE4B5
```

## Complete Integration Flow

*End-to-end system view: scheduler triggers alert application → writes health status file → Docker healthcheck reads file → reports to Docker Engine → health monitor detects unhealthy containers → Phase 2 recheck → sends email alerts*
```mermaid
flowchart TD
    subgraph Container[Docker Container]
        App[Python Application<br/>src main.py]
        Alert[BaseAlert.run]
        Health[app logs<br/>health_status.txt]
        HCScript[scripts healthcheck.py]
    end
    
    subgraph Docker[Docker Engine]
        HealthCheck[HEALTHCHECK<br/>interval 2m]
        Status[Container Status<br/>healthy unhealthy starting]
    end
    
    subgraph Monitor[Health Monitor]
        Phase1[Phase 1<br/>Check All Containers]
        Phase2[Phase 2<br/>Recheck Unhealthy]
        Email[Send Alert Email<br/>with Logs]
    end
    
    Schedule[Scheduler<br/>APScheduler or Cron] -->|Triggers| App
    App -->|Calls| Alert
    
    Alert -->|Success| WriteOK[Write OK plus timestamp]
    Alert -->|Exception| WriteERROR[Write ERROR plus msg]
    
    WriteOK -->|Updates| Health
    WriteERROR -->|Updates| Health
    
    HealthCheck -->|Every 2 min| HCScript
    HCScript -->|Reads| Health
    
    HCScript -->|Exit 0| Healthy[healthy]
    HCScript -->|Exit 1| Unhealthy[unhealthy]
    
    Healthy --> Status
    Unhealthy --> Status
    
    Phase1 -->|Polls Docker API| Status
    Status -->|If unhealthy| Phase2
    Phase2 -->|Still unhealthy<br/>after 15 min| Email
    
    style WriteOK fill:#90EE90
    style WriteERROR fill:#FF6B6B
    style Healthy fill:#90EE90
    style Unhealthy fill:#FF6B6B
    style Email fill:#FFB6C1
```

## Example Error Scenarios

### Scenario 1: Database Down
*Alert application encounters database connection error → writes ERROR to health file → healthcheck detects ERROR status → container marked unhealthy → Phase 2 confirms and sends alert*
```mermaid
flowchart LR
    S1A[12:00<br/>Scheduler<br/>triggers]
    S1B[fetch_data<br/>raises<br/>OperationalError]
    S1C[Exception<br/>caught<br/>logs traceback]
    S1D[Writes<br/>ERROR<br/>DB failed]
    S1E[12:02<br/>Healthcheck<br/>runs]
    S1F[Reads<br/>ERROR]
    S1G[Container<br/>unhealthy]
    S1H[12:17<br/>Phase 2<br/>recheck]
    S1I[Still<br/>unhealthy]
    S1J[Alert sent<br/>with logs]
    
    S1A --> S1B --> S1C --> S1D --> S1E --> S1F --> S1G --> S1H --> S1I --> S1J
    
    style S1D fill:#FF6B6B
    style S1G fill:#FF6B6B
    style S1J fill:#FFB6C1
```

### Scenario 2: SMTP Failed
*Alert application runs successfully but SMTP fails during notification sending → still writes OK (partial success) → container stays healthy → no external alert sent but error logged*
```mermaid
flowchart LR
    S2A[12:00<br/>Scheduler<br/>triggers]
    S2B[fetch_data<br/>OK]
    S2C[filter_data<br/>OK]
    S2D[route_notifications<br/>OK]
    S2E[send_notifications<br/>SMTP error]
    S2F[Logs<br/>Failed to send<br/>continues]
    S2G[Writes<br/>OK<br/>partial success]
    S2H[Container<br/>healthy]
    S2I[No alert<br/>error in logs]
    
    S2A --> S2B --> S2C --> S2D --> S2E --> S2F --> S2G --> S2H --> S2I
    
    style S2G fill:#90EE90
    style S2H fill:#90EE90
    style S2I fill:#FFE4B5
```

### Scenario 3: Scheduler Not Running
*Scheduler crashes and stops triggering alert application → health file becomes stale (6 hours old) → healthcheck detects file age exceeds maximum → container marked unhealthy → alert sent*
```mermaid
flowchart LR
    S3A[12:00<br/>No trigger<br/>Crashed]
    S3B[health_status.txt<br/>modified 06:00]
    S3C[12:02<br/>Healthcheck<br/>runs]
    S3D[File age<br/>362 min]
    S3E[Max age<br/>130 min]
    S3F[File<br/>too old]
    S3G[Container<br/>unhealthy]
    S3H[12:17<br/>Alert sent]
    
    S3A --> S3B --> S3C --> S3D --> S3E --> S3F --> S3G --> S3H
    
    style S3F fill:#FF6B6B
    style S3G fill:#FF6B6B
```

## Summary Table

| Condition | health_status.txt | Healthcheck Result | Container Status | Alert Sent After 15 Min |
|-----------|-------------------|-------------------|------------------|------------------------|
| **App runs successfully, no data** | `OK 12:00:00` | Exit 0 | healthy | No |
| **App runs successfully, sent emails** | `OK 12:05:00` | Exit 0 | healthy | No |
| **Database connection failed** | `ERROR 12:00:00`<br/>`ERROR_MSG: Connection refused` | Exit 1 | unhealthy | Yes (with logs) |
| **Missing required columns** | `ERROR 12:00:00`<br/>`ERROR_MSG: Missing columns` | Exit 1 | unhealthy | Yes (with logs) |
| **Scheduler not running** | `OK 06:00:00` (old) | Exit 1 (too old) | unhealthy | Yes (with logs) |
| **File doesn't exist** | (missing) | Exit 1 | unhealthy | Yes (with logs) |
| **File unreadable** | (permission error) | Exit 1 | unhealthy | Yes (with logs) |
| **App crashed before writing** | (missing or old) | Exit 1 | unhealthy | Yes (with logs) |

These diagrams make it crystal clear:
1. **When healthchecks pass** (green paths)
2. **When healthchecks fail** (red paths)
3. **What exceptions in `base_alert.py` lead to failures**
4. **How the monitoring system responds**
