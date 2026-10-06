// ─────────────────────────────────────────────────────────────────────────────
// Alerting (roadmap Phase 5):
//   - per-app Container Apps alerts: CPU %, memory %, replica health, restarts
//   - database (Postgres Flexible Server) alerts: availability, CPU, memory,
//     connection saturation, failed connections, storage
//   - error-severity spike on the logs table (AppTraces)
//   - Service Health + Resource Health activity-log alerts (free)
// Every rule notifies the shared action group. All metric names verified
// against the Azure Monitor supported-metrics reference (Microsoft.App/
// containerapps and Microsoft.DBforPostgreSQL/flexibleServers).
// ─────────────────────────────────────────────────────────────────────────────

@description('Base name used in alert resource names.')
param baseName string

@description('Region for the log-query alert rule (metric/activity alerts are global).')
param location string

@description('Action group every rule notifies.')
param actionGroupId string

@description('Log Analytics workspace backing App Insights (scope of the error-spike alert).')
param workspaceId string

@description('''
Container Apps to monitor: array of { name: string, resourceId: string }.
Empty (default) = skip per-app alerts — the apps are not deployed yet
(deployment is Planned; see README "Scope & delivery status").
''')
param containerApps array = []

@description('CPU alert threshold, percent of the app CPU limit.')
param cpuThresholdPercent int = 80

@description('Memory alert threshold, percent of the app memory limit.')
param memoryThresholdPercent int = 80

@description('Replica-health: alert when average replica count drops below this.')
param minReplicas int = 1

@description('''
Restart alert threshold. NOTE: RestartCount is CUMULATIVE per replica since
its creation — a healthy long-lived replica keeps a stable count, a crash
loop climbs fast. The alert uses Maximum over the window; expect it to stay
firing until the crash-looping revision is replaced.
''')
param restartCountThreshold int = 5

@description('Resource ID of the external Azure Postgres Flexible Server. Empty (default) = skip DB alerts.')
param postgresServerId string = ''

@description('Database CPU alert threshold (percent).')
param dbCpuThresholdPercent int = 80

@description('Database memory alert threshold (percent).')
param dbMemoryThresholdPercent int = 85

@description('Database storage alert threshold (percent).')
param dbStorageThresholdPercent int = 80

@description('''
Connection-saturation threshold as an ABSOLUTE active-connection count.
Metric alerts cannot divide by the max_connections metric, so set this to
~80% of your SKU's max_connections (check: SHOW max_connections;).
''')
param dbActiveConnectionsThreshold int = 400

@description('Failed-connections alert threshold (count per 15 min).')
param dbFailedConnectionsThreshold int = 10

@description('Error-severity log spike: AppTraces rows with SeverityLevel >= 3 per 15 min.')
param errorSpikeThreshold int = 25

@description('Deploy the (free) Service Health + Resource Health activity-log alerts.')
param enableServiceHealthAlerts bool = true

var appAlertDefs = [
  {
    suffix: 'cpu'
    description: 'CPU above ${cpuThresholdPercent}% of the app CPU limit.'
    metricName: 'CpuPercentage'
    operator: 'GreaterThan'
    threshold: cpuThresholdPercent
    timeAggregation: 'Average'
    severity: 3
  }
  {
    suffix: 'memory'
    description: 'Memory above ${memoryThresholdPercent}% of the app memory limit.'
    metricName: 'MemoryPercentage'
    operator: 'GreaterThan'
    threshold: memoryThresholdPercent
    timeAggregation: 'Average'
    severity: 3
  }
  {
    suffix: 'replicas'
    description: 'Average replica count below ${minReplicas} — the app is under-provisioned or failing to schedule.'
    metricName: 'Replicas'
    operator: 'LessThan'
    threshold: minReplicas
    timeAggregation: 'Average'
    severity: 2
  }
  {
    suffix: 'restarts'
    description: 'Replica restart count at or above ${restartCountThreshold} — likely a crash loop.'
    metricName: 'RestartCount'
    operator: 'GreaterThanOrEqual'
    threshold: restartCountThreshold
    timeAggregation: 'Maximum'
    severity: 2
  }
]

// One flattened loop: containerApps × appAlertDefs.
var appAlertInstances = [
  for pair in flatten(map(containerApps, app => map(appAlertDefs, def => { app: app, def: def }))): pair
]

resource containerAppAlerts 'Microsoft.Insights/metricAlerts@2018-03-01' = [
  for inst in appAlertInstances: {
    name: 'alert-${inst.app.name}-${inst.def.suffix}'
    location: 'global'
    properties: {
      description: '${inst.app.name}: ${inst.def.description}'
      severity: inst.def.severity
      enabled: true
      scopes: [inst.app.resourceId]
      evaluationFrequency: 'PT5M'
      windowSize: 'PT15M'
      criteria: {
        'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
        allOf: [
          {
            criterionType: 'StaticThresholdCriterion'
            name: inst.def.suffix
            metricNamespace: 'microsoft.app/containerapps'
            metricName: inst.def.metricName
            operator: inst.def.operator
            threshold: inst.def.threshold
            timeAggregation: inst.def.timeAggregation
          }
        ]
      }
      autoMitigate: true
      actions: [
        {
          actionGroupId: actionGroupId
        }
      ]
    }
  }
]

var dbAlertDefs = [
  {
    suffix: 'db-alive'
    description: 'Database availability signal (is_db_alive) dropped below 1.'
    metricName: 'is_db_alive'
    operator: 'LessThan'
    threshold: 1
    timeAggregation: 'Average'
    severity: 0
  }
  {
    suffix: 'db-cpu'
    description: 'Database CPU above ${dbCpuThresholdPercent}%.'
    metricName: 'cpu_percent'
    operator: 'GreaterThan'
    threshold: dbCpuThresholdPercent
    timeAggregation: 'Average'
    severity: 2
  }
  {
    suffix: 'db-memory'
    description: 'Database memory above ${dbMemoryThresholdPercent}%.'
    metricName: 'memory_percent'
    operator: 'GreaterThan'
    threshold: dbMemoryThresholdPercent
    timeAggregation: 'Average'
    severity: 2
  }
  {
    suffix: 'db-connections'
    description: 'Active connections above ${dbActiveConnectionsThreshold} (~saturation; threshold ≈ 80% of the SKU max_connections).'
    metricName: 'active_connections'
    operator: 'GreaterThan'
    threshold: dbActiveConnectionsThreshold
    timeAggregation: 'Average'
    severity: 2
  }
  {
    suffix: 'db-failed-connections'
    description: 'More than ${dbFailedConnectionsThreshold} failed connections in 15 min.'
    metricName: 'connections_failed'
    operator: 'GreaterThan'
    threshold: dbFailedConnectionsThreshold
    timeAggregation: 'Total'
    severity: 2
  }
  {
    suffix: 'db-storage'
    description: 'Database storage above ${dbStorageThresholdPercent}% — Postgres goes read-only when storage fills.'
    metricName: 'storage_percent'
    operator: 'GreaterThan'
    threshold: dbStorageThresholdPercent
    timeAggregation: 'Average'
    severity: 1
  }
]

resource postgresAlerts 'Microsoft.Insights/metricAlerts@2018-03-01' = [
  for def in dbAlertDefs: if (!empty(postgresServerId)) {
    name: 'alert-${baseName}-${def.suffix}'
    location: 'global'
    properties: {
      description: def.description
      severity: def.severity
      enabled: true
      scopes: [postgresServerId]
      evaluationFrequency: 'PT5M'
      windowSize: 'PT15M'
      criteria: {
        'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
        allOf: [
          {
            criterionType: 'StaticThresholdCriterion'
            name: def.suffix
            metricNamespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
            metricName: def.metricName
            operator: def.operator
            threshold: def.threshold
            timeAggregation: def.timeAggregation
          }
        ]
      }
      autoMitigate: true
      actions: [
        {
          actionGroupId: actionGroupId
        }
      ]
    }
  }
]

// Error-severity spike on the logs table. SeverityLevel >= 3 == Error/Critical
// (the services' log bridges map error/fatal levels there).
resource errorSpikeAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'alert-${baseName}-error-spike'
  location: location
  properties: {
    displayName: 'Error-severity log spike (${baseName})'
    description: 'More than ${errorSpikeThreshold} error-severity rows in AppTraces within 15 minutes.'
    severity: 2
    enabled: true
    scopes: [workspaceId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      allOf: [
        {
          query: 'AppTraces | where SeverityLevel >= 3'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: errorSpikeThreshold
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: true
    actions: {
      actionGroups: [actionGroupId]
    }
  }
}

// Free platform alerts: Azure incidents (ServiceHealth) + per-resource health
// transitions (ResourceHealth), subscription-scoped.
resource serviceHealthAlert 'Microsoft.Insights/activityLogAlerts@2020-10-01' = if (enableServiceHealthAlerts) {
  name: 'alert-${baseName}-service-health'
  location: 'global'
  properties: {
    enabled: true
    scopes: [subscription().id]
    condition: {
      allOf: [
        {
          field: 'category'
          equals: 'ServiceHealth'
        }
      ]
    }
    actions: {
      actionGroups: [
        {
          actionGroupId: actionGroupId
        }
      ]
    }
  }
}

resource resourceHealthAlert 'Microsoft.Insights/activityLogAlerts@2020-10-01' = if (enableServiceHealthAlerts) {
  name: 'alert-${baseName}-resource-health'
  location: 'global'
  properties: {
    enabled: true
    scopes: [subscription().id]
    condition: {
      allOf: [
        {
          field: 'category'
          equals: 'ResourceHealth'
        }
      ]
    }
    actions: {
      actionGroups: [
        {
          actionGroupId: actionGroupId
        }
      ]
    }
  }
}
