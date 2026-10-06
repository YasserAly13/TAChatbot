// dev — names and sizes only. No secrets, ever (ADR-0012). Per-developer overrides go in a
// gitignored main.dev.local.bicepparam. The pipeline overrides apiImage/webImage with the tags
// it just pushed; the values below are what `make infra-deploy ENV=dev` uses from a laptop.
using './main.bicep'

param environment = 'dev'
param projectSlug = 'team-assistant'
param platform = loadJsonContent('platform/dev.json')

// Step 1 of the first deployment: false until the cloud team has granted the roles in
// infra/grant-request.md (AcrPull above all). Then true.
param deployContainerApps = false

param apiImage = '${loadJsonContent('platform/dev.json').containerRegistry.loginServer}/team-assistant-api:dev'
param webImage = '${loadJsonContent('platform/dev.json').containerRegistry.loginServer}/team-assistant-web:dev'

// Entra admin of the SQL server — a group is recommended. Object IDs are not secrets.
param sqlEntraAdmin = {
  login: 'ai-dev-sql-admins'
  objectId: '00000000-0000-0000-0000-000000000000'
  principalType: 'Group'
}
param sqlSku = { name: 'GP_S_Gen5', tier: 'GeneralPurpose', family: 'Gen5', capacity: 1 }
param developerIpAllowlist = {
  // alice: '203.0.113.10'
}

param alertEmails = ['ops@example.invalid']
param retentionInDays = 30
param logAnalyticsDailyCapGb = -1
param dailyIngestionAlertThresholdGb = 5
param storageContainers = ['uploads']
param keyVaultPurgeProtection = false
param apiReplicas = { min: 1, max: 2 }
param webReplicas = { min: 1, max: 2 }
param logLevel = 'debug'
