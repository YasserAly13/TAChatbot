// ─────────────────────────────────────────────────────────────────────────────
// AI Accelerator — the USE-CASE tier of one project, per environment (ADR-0012).
//
// Two tiers:
//   • PLATFORM tier (cloud team, shared by every use case, pre-exists): Azure AI Foundry
//     + model deployments, Container Apps Environment, Container Registry, AI Search
//     service. Described by infra/platform/<env>.json, referenced below with `existing`.
//     Nothing here creates, changes or grants on them.
//   • USE-CASE tier (this file): identities, Log Analytics + App Insights + alerts,
//     Key Vault, Azure SQL, storage, and the two container apps — composed from the
//     building blocks in infra/modules/ (the infra team's; placeholders marked ⚠ until
//     their files arrive).
//
// Two-step first deployment (the identities must be granted AcrPull before an app can pull):
//   1. deployContainerApps = false → identities, observability, Key Vault, SQL, storage;
//      outputs the principal IDs → scripts/grant-request.mjs → infra/grant-request.md →
//      the cloud team grants (AcrPull, Cognitive Services OpenAI User, Search roles).
//   2. deployContainerApps = true → the apps, alerts and availability tests.
//
// Deploy: `make infra-whatif ENV=dev` → review → `make infra-deploy ENV=dev` (humans, dev only);
// staging/prod via .github/workflows/infra.yml. Agents: `make infra-build` only.
// ─────────────────────────────────────────────────────────────────────────────

targetScope = 'resourceGroup'

// ── Types ───────────────────────────────────────────────────────────────────

@description('The platform manifest (infra/platform/<env>.json) — names of the shared tier.')
type Platform = {
  environment: 'dev' | 'staging' | 'prod'
  subscriptionId: string
  location: string
  resourceGroup: string
  containerAppsEnvironment: { name: string, resourceGroup: string }
  containerRegistry: { name: string, loginServer: string, resourceGroup: string }
  aiFoundry: {
    name: string
    resourceGroup: string
    endpoint: string
    deployments: { chat: string, embedding: string, embeddingDimensions: int }
  }
  aiSearch: { name: string, resourceGroup: string, endpoint: string }
  tags: object?
}

// ── Identity of the use case ─────────────────────────────────────────────────

@description('Project slug (kebab-case, ≤ 15 chars). Drives every resource name; /rename-project rewrites it.')
@minLength(3)
@maxLength(15)
param projectSlug string = 'ai-accelerator'

@allowed(['dev', 'staging', 'prod'])
param environment string

@description('The shared tier for this environment — `loadJsonContent(\'platform/<env>.json\')` in the param file.')
param platform Platform

@description('Region for owned resources (defaults to the manifest\'s).')
param location string = platform.location

// ── Images (overridden by the pipeline with the just-pushed tags) ────────────

@description('Full api image reference on the shared registry.')
param apiImage string

@description('Full web image reference on the shared registry.')
param webImage string

@description('false for the very first deployment (identities need AcrPull first) — see header.')
param deployContainerApps bool = true

// ── Database (D6) ────────────────────────────────────────────────────────────

@description('Entra admin of the SQL server: { login, objectId, principalType }. A group is recommended.')
param sqlEntraAdmin object

@description('Database SKU object (see modules/sql-database.bicep).')
param sqlSku object = { name: 'GP_S_Gen5', tier: 'GeneralPurpose', family: 'Gen5', capacity: 1 }

@description('Developer IPs allowed through the SQL firewall: { alice: "203.0.113.10" }. Empty in prod.')
param developerIpAllowlist object = {}

// ── Search index (D7 — the index is ours, the service is shared) ─────────────

@description('AI Search index name; must be unique on the shared service. Default <slug>-docs.')
param searchIndexName string = '${projectSlug}-docs'

// ── Apps ─────────────────────────────────────────────────────────────────────

@description('Replica bounds per app.')
param apiReplicas object = { min: 1, max: 3 }
param webReplicas object = { min: 1, max: 3 }

@description('LOG_LEVEL for both services.')
param logLevel string = 'info'

@description('TELEMETRY_AUTH_MODE for both apps: connection_string (default) or managed_identity — the latter needs Monitoring Metrics Publisher granted by the cloud team (grant-request.md) first.')
@allowed(['connection_string', 'managed_identity'])
param telemetryAuthMode string = 'connection_string'

@description('Reject unauthenticated telemetry ingestion. Only after telemetryAuthMode = managed_identity has been verified to flow.')
param disableLocalTelemetryAuth bool = false

// ── Observability + alerting (template-owned modules) ────────────────────────

@description('Email recipients for every alert.')
param alertEmails array = []

@description('Optional webhook added to the action group.')
param alertWebhookUrl string = ''

@description('Log Analytics retention in days.')
param retentionInDays int = 30

@description('Workspace daily cap in GB (-1 = uncapped).')
param logAnalyticsDailyCapGb int = -1

@description('Daily billable-ingestion alert threshold (GB/day).')
param dailyIngestionAlertThresholdGb int = 5

@description('Blob containers to create in the use case\'s storage account.')
param storageContainers array = ['uploads']

@description('Key Vault purge protection (true in prod; irreversible).')
param keyVaultPurgeProtection bool = false

// ── Names (one convention, overridable only by editing here) ─────────────────

var slugCompact = replace(projectSlug, '-', '')
var baseName = '${projectSlug}-${environment}'
var tags = union(platform.?tags ?? {}, { project: projectSlug, environment: environment, managedBy: 'bicep' })

var names = {
  apiIdentity: 'id-${baseName}-api'
  webIdentity: 'id-${baseName}-web'
  keyVault: 'kv-${take(projectSlug, 13)}-${environment}' // ≤ 24 chars
  sqlServer: 'sql-${baseName}'
  sqlDatabase: 'sqldb-${baseName}'
  storage: take('st${slugCompact}${environment}', 24)
  apiApp: 'ca-${baseName}-api'
  webApp: 'ca-${baseName}-web'
  actionGroup: 'ag-${baseName}'
}

// ── Platform tier — referenced, never created ────────────────────────────────

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: platform.containerAppsEnvironment.name
  scope: resourceGroup(platform.containerAppsEnvironment.resourceGroup)
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: platform.containerRegistry.name
  scope: resourceGroup(platform.containerRegistry.resourceGroup)
}

resource aiFoundry 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: platform.aiFoundry.name
  scope: resourceGroup(platform.aiFoundry.resourceGroup)
}

resource aiSearch 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: platform.aiSearch.name
  scope: resourceGroup(platform.aiSearch.resourceGroup)
}

// ── Identities ───────────────────────────────────────────────────────────────

module apiIdentity 'modules/user-assigned-identity.bicep' = {
  name: 'identity-api'
  params: { name: names.apiIdentity, location: location, tags: tags }
}

module webIdentity 'modules/user-assigned-identity.bicep' = {
  name: 'identity-web'
  params: { name: names.webIdentity, location: location, tags: tags }
}

// ── Observability (Log Analytics + workspace-based App Insights + cost alert) ─

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: names.actionGroup
  location: 'global'
  tags: tags
  properties: {
    groupShortName: take(replace(baseName, '-', ''), 12)
    enabled: true
    emailReceivers: [
      for (email, i) in alertEmails: { name: 'email-${i}', emailAddress: email, useCommonAlertSchema: true }
    ]
    webhookReceivers: empty(alertWebhookUrl)
      ? []
      : [{ name: 'webhook', serviceUri: alertWebhookUrl, useCommonAlertSchema: true }]
  }
}

module observability 'modules/observability.bicep' = {
  name: 'observability'
  params: {
    baseName: baseName
    location: location
    retentionInDays: retentionInDays
    logAnalyticsDailyCapGb: logAnalyticsDailyCapGb
    dailyIngestionAlertThresholdGb: dailyIngestionAlertThresholdGb
    // Entra-only ingestion needs Monitoring Metrics Publisher on the component — a role
    // assignment the deployment identity (Contributor) cannot create: request it, then flip.
    disableLocalAuth: disableLocalTelemetryAuth
    telemetryPublisherPrincipalIds: []
    actionGroupId: actionGroup.id
  }
}

// ── Database ─────────────────────────────────────────────────────────────────

module sql 'modules/sql-database.bicep' = {
  name: 'sql'
  params: {
    serverName: names.sqlServer
    databaseName: names.sqlDatabase
    location: location
    tags: tags
    entraAdmin: sqlEntraAdmin
    sku: sqlSku
    developerIpAllowlist: developerIpAllowlist
    zoneRedundant: environment == 'prod'
  }
}

// The api connects as its managed identity — no password exists (ADR-0008).
var databaseUrl = 'mssql+aioodbc://@${sql.outputs.serverFqdn}:1433/${sql.outputs.databaseName}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&Authentication=ActiveDirectoryMsi&UID=${apiIdentity.outputs.clientId}'

// ── Storage ──────────────────────────────────────────────────────────────────

module storage 'modules/storage-account.bicep' = {
  name: 'storage'
  params: {
    name: names.storage
    location: location
    tags: tags
    skuName: environment == 'prod' ? 'Standard_ZRS' : 'Standard_LRS'
    containers: storageContainers
  }
}

// ── Key Vault — the strings the apps read ────────────────────────────────────

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    name: names.keyVault
    location: location
    tags: tags
    secretReaderPrincipalIds: [apiIdentity.outputs.principalId, webIdentity.outputs.principalId]
    secretOfficerPrincipalIds: [deployer().objectId]
    secretNames: ['APPLICATIONINSIGHTS-CONNECTION-STRING', 'DATABASE-URL']
    secrets: {
      'APPLICATIONINSIGHTS-CONNECTION-STRING': observability.outputs.connectionString
      'DATABASE-URL': databaseUrl
    }
    purgeProtectionEnabled: keyVaultPurgeProtection
    softDeleteRetentionInDays: environment == 'prod' ? 90 : 7
  }
}

// ── Container apps (step 2) ──────────────────────────────────────────────────

var commonEnv = {
  APP_ENV: environment
  LOG_LEVEL: logLevel
  TELEMETRY_AUTH_MODE: telemetryAuthMode
}

module apiApp 'modules/container-app.bicep' = if (deployContainerApps) {
  name: 'app-api'
  params: {
    name: names.apiApp
    location: location
    tags: tags
    environmentId: containerAppsEnvironment.id
    identityId: apiIdentity.outputs.id
    image: apiImage
    registryServer: platform.containerRegistry.loginServer
    targetPort: 8000
    externalIngress: false
    minReplicas: apiReplicas.min
    maxReplicas: apiReplicas.max
    env: union(commonEnv, {
      PORT: '8000'
      OTEL_SERVICE_NAME: '${projectSlug}-api'
      // DefaultAzureCredential picks the user-assigned identity by this id.
      AZURE_CLIENT_ID: apiIdentity.outputs.clientId
      TELEMETRY_MANAGED_IDENTITY_CLIENT_ID: apiIdentity.outputs.clientId
      AZURE_AI_ENDPOINT: platform.aiFoundry.endpoint
      AZURE_AI_DEPLOYMENT: platform.aiFoundry.deployments.chat
      AZURE_AI_EMBEDDING_DEPLOYMENT: platform.aiFoundry.deployments.embedding
      AZURE_AI_EMBEDDING_DIMENSIONS: string(platform.aiFoundry.deployments.embeddingDimensions)
      AZURE_AI_AUTH_MODE: 'managed_identity'
      AZURE_SEARCH_ENDPOINT: platform.aiSearch.endpoint
      AZURE_SEARCH_INDEX: searchIndexName
      AZURE_STORAGE_ACCOUNT: storage.outputs.name
    })
    keyVaultEnvRefs: {
      APPLICATIONINSIGHTS_CONNECTION_STRING: '${keyVault.outputs.uri}secrets/APPLICATIONINSIGHTS-CONNECTION-STRING'
      DATABASE_URL: '${keyVault.outputs.uri}secrets/DATABASE-URL'
    }
  }
}

module webApp 'modules/container-app.bicep' = if (deployContainerApps) {
  name: 'app-web'
  params: {
    name: names.webApp
    location: location
    tags: tags
    environmentId: containerAppsEnvironment.id
    identityId: webIdentity.outputs.id
    image: webImage
    registryServer: platform.containerRegistry.loginServer
    targetPort: 3000
    externalIngress: true
    minReplicas: webReplicas.min
    maxReplicas: webReplicas.max
    env: union(commonEnv, {
      PORT: '3000'
      OTEL_SERVICE_NAME: '${projectSlug}-web'
      AZURE_CLIENT_ID: webIdentity.outputs.clientId
      TELEMETRY_MANAGED_IDENTITY_CLIENT_ID: webIdentity.outputs.clientId
      // The BFF reaches the api inside the environment (internal ingress).
      API_BASE_URL: 'https://${apiApp.?outputs.fqdn ?? ''}'
    })
    keyVaultEnvRefs: {
      APPLICATIONINSIGHTS_CONNECTION_STRING: '${keyVault.outputs.uri}secrets/APPLICATIONINSIGHTS-CONNECTION-STRING'
    }
  }
}

// ── Alerts + availability (template-owned modules; apps only once deployed) ──

module alerts 'modules/alerts.bicep' = {
  name: 'alerts'
  params: {
    baseName: baseName
    location: location
    actionGroupId: actionGroup.id
    workspaceId: observability.outputs.workspaceId
    containerApps: deployContainerApps
      ? [
          { name: 'web', resourceId: webApp.?outputs.id ?? '' }
          { name: 'api', resourceId: apiApp.?outputs.id ?? '' }
        ]
      : []
    minReplicas: min(apiReplicas.min, webReplicas.min)
    // Azure SQL metric alerts are a follow-up (the module's DB rules target Postgres).
    postgresServerId: ''
    enableServiceHealthAlerts: false
  }
}

module availability 'modules/availability.bicep' = {
  name: 'availability'
  params: {
    baseName: baseName
    location: location
    appInsightsId: observability.outputs.appInsightsId
    actionGroupId: actionGroup.id
    webTests: deployContainerApps ? [{ name: 'web-health', url: 'https://${webApp.?outputs.fqdn ?? ''}/health' }] : []
  }
}

// ── Outputs ──────────────────────────────────────────────────────────────────

output webUrl string = deployContainerApps ? 'https://${webApp.?outputs.fqdn ?? ''}' : ''
output apiInternalFqdn string = deployContainerApps ? (apiApp.?outputs.fqdn ?? '') : ''
output keyVaultUri string = keyVault.outputs.uri
output sqlServerFqdn string = sql.outputs.serverFqdn
output sqlDatabaseName string = sql.outputs.databaseName
output storageAccountName string = storage.outputs.name
output searchIndexName string = searchIndexName
output apiIdentityName string = apiIdentity.outputs.name
output apiIdentityClientId string = apiIdentity.outputs.clientId
output apiIdentityPrincipalId string = apiIdentity.outputs.principalId
output webIdentityPrincipalId string = webIdentity.outputs.principalId

@description('Roles this use case needs on SHARED resources (D11). Rendered by scripts/grant-request.mjs into infra/grant-request.md for the cloud team. Never assigned here.')
output grantRequest array = [
  {
    identity: names.apiIdentity
    principalId: apiIdentity.outputs.principalId
    role: 'AcrPull'
    scope: containerRegistry.id
    why: 'pull the api image'
  }
  {
    identity: names.webIdentity
    principalId: webIdentity.outputs.principalId
    role: 'AcrPull'
    scope: containerRegistry.id
    why: 'pull the web image'
  }
  {
    identity: names.apiIdentity
    principalId: apiIdentity.outputs.principalId
    role: 'Cognitive Services OpenAI User'
    scope: aiFoundry.id
    why: 'chat + embedding calls (AZURE_AI_AUTH_MODE=managed_identity)'
  }
  {
    identity: names.apiIdentity
    principalId: apiIdentity.outputs.principalId
    role: 'Search Index Data Reader'
    scope: aiSearch.id
    why: 'retrieval queries on index ${searchIndexName}'
  }
  {
    identity: names.apiIdentity
    principalId: apiIdentity.outputs.principalId
    role: 'Search Index Data Contributor'
    scope: aiSearch.id
    why: 'ingestion writes documents to index ${searchIndexName}'
  }
  {
    identity: names.apiIdentity
    principalId: apiIdentity.outputs.principalId
    role: 'Search Service Contributor'
    scope: aiSearch.id
    why: 'ingestion creates/updates the index definition'
  }
  {
    identity: names.apiIdentity
    principalId: apiIdentity.outputs.principalId
    role: 'Storage Blob Data Contributor'
    scope: storage.outputs.id
    why: 'own storage — listed because the deployment identity cannot assign roles'
  }
]
