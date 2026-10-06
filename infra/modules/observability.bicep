// ─────────────────────────────────────────────────────────────────────────────
// Observability backend (roadmap Phase 4):
//   Log Analytics workspace  →  WORKSPACE-BASED Application Insights (never
//   classic), plus the cost guardrail (daily billable-ingestion alert) and
//   optional ingestion hardening (Monitoring Metrics Publisher role
//   assignments + DisableLocalAuth).
// The apps consume ONE output: the connection string
// (APPLICATIONINSIGHTS_CONNECTION_STRING) — same code path locally & deployed.
// ─────────────────────────────────────────────────────────────────────────────

@description('Base name used for resource names (log-<baseName>, appi-<baseName>).')
param baseName string

@description('Azure region for the workspace + component.')
param location string

@description('Log Analytics data retention in days (default 30 = the free retention window).')
@minValue(30)
@maxValue(730)
param retentionInDays int = 30

@description('''
Workspace DAILY CAP in GB — the hard switch that stops ingestion for the rest
of the day once exceeded (data is DROPPED beyond the cap). -1 = no cap
(default). Prefer the ingestion ALERT below as the first guardrail and this
cap as the emergency brake; tune telemetry volume with the TRACE_SAMPLING_RATIO
env var (see the repo observability rule).
''')
param logAnalyticsDailyCapGb int = -1

@description('''
Ingestion hardening: when true, the component REJECTS connection-string-only
(unauthenticated) telemetry — only Microsoft Entra ID-authenticated senders
(Monitoring Metrics Publisher role) can ingest. Flip this ONLY after the apps
run with TELEMETRY_AUTH_MODE=managed_identity and their identities are listed
in telemetryPublisherPrincipalIds, or telemetry stops silently server-side.
''')
param disableLocalAuth bool = false

@description('''
Principal IDs (managed identity object IDs of the web/api apps) to be
granted "Monitoring Metrics Publisher" on the component so they can ingest
with Entra ID auth.
''')
param telemetryPublisherPrincipalIds array = []

@description('Daily billable-ingestion alert threshold in GB/day (cost guardrail).')
param dailyIngestionAlertThresholdGb int = 5

@description('Action group the ingestion alert notifies.')
param actionGroupId string

// Built-in role: Monitoring Metrics Publisher (publishes ALL telemetry, not
// just metrics). GUID verified against the Azure built-in roles reference.
var monitoringMetricsPublisherRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '3913510d-42f4-4e42-8a64-420c390055eb'
)

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${baseName}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
    workspaceCapping: {
      dailyQuotaGb: logAnalyticsDailyCapGb
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${baseName}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
    DisableLocalAuth: disableLocalAuth
  }
}

resource publisherRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principalId in telemetryPublisherPrincipalIds: {
    name: guid(appInsights.id, principalId, monitoringMetricsPublisherRoleId)
    scope: appInsights
    properties: {
      roleDefinitionId: monitoringMetricsPublisherRoleId
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]

// Cost guardrail: fires when billable ingestion over the last day crosses the
// threshold. Query shape per the Azure Monitor usage-alert guidance
// (Usage.Quantity is in MB; IsBillable excludes free data types).
resource dailyIngestionAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'alert-${baseName}-daily-ingestion'
  location: location
  properties: {
    displayName: 'Billable ingestion above ${dailyIngestionAlertThresholdGb} GB/day (${baseName})'
    description: 'Cost guardrail: workspace billable ingestion over the trailing 24 h crossed the threshold. Tune TRACE_SAMPLING_RATIO or investigate a log flood; the workspace daily cap is the emergency brake.'
    severity: 2
    enabled: true
    scopes: [workspace.id]
    evaluationFrequency: 'PT1H'
    windowSize: 'P1D'
    criteria: {
      allOf: [
        {
          query: 'Usage | where IsBillable == true | summarize DataGB = sum(Quantity) / 1000.0'
          timeAggregation: 'Total'
          metricMeasureColumn: 'DataGB'
          operator: 'GreaterThan'
          threshold: dailyIngestionAlertThresholdGb
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

output workspaceId string = workspace.id
output appInsightsId string = appInsights.id
@description('Wire this into each app as APPLICATIONINSIGHTS_CONNECTION_STRING (via Key Vault / Container Apps secret — never commit it).')
output connectionString string = appInsights.properties.ConnectionString
