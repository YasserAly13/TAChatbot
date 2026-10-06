// staging — names and sizes only. No secrets, ever (ADR-0012). Deployed by .github/workflows/infra.yml
// on merge to `staging`; the pipeline overrides apiImage/webImage with the tags it just pushed.
using './main.bicep'

param environment = 'staging'
param projectSlug = 'ai-accelerator'
param platform = loadJsonContent('platform/staging.json')

param deployContainerApps = false

param apiImage = '${loadJsonContent('platform/staging.json').containerRegistry.loginServer}/ai-accelerator-api:staging'
param webImage = '${loadJsonContent('platform/staging.json').containerRegistry.loginServer}/ai-accelerator-web:staging'

param sqlEntraAdmin = {
  login: 'ai-stg-sql-admins'
  objectId: '00000000-0000-0000-0000-000000000000'
  principalType: 'Group'
}
param sqlSku = { name: 'S0', tier: 'Standard' }
param developerIpAllowlist = {}

param alertEmails = ['ops@example.invalid']
param retentionInDays = 30
param logAnalyticsDailyCapGb = -1
param dailyIngestionAlertThresholdGb = 5
param storageContainers = ['uploads']
param keyVaultPurgeProtection = false
param apiReplicas = { min: 1, max: 3 }
param webReplicas = { min: 1, max: 3 }
param logLevel = 'info'
