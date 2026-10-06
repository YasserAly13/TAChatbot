// prod — names and sizes only. No secrets, ever (ADR-0012). Deployed by .github/workflows/infra.yml
// on merge to `main`, behind the `prod` GitHub Environment's reviewers; the pipeline overrides
// apiImage/webImage with the tags it just pushed. No developer IPs, purge protection on.
using './main.bicep'

param environment = 'prod'
param projectSlug = 'team-assistant'
param platform = loadJsonContent('platform/prod.json')

param deployContainerApps = false

param apiImage = '${loadJsonContent('platform/prod.json').containerRegistry.loginServer}/team-assistant-api:prod'
param webImage = '${loadJsonContent('platform/prod.json').containerRegistry.loginServer}/team-assistant-web:prod'

param sqlEntraAdmin = {
  login: 'ai-prod-sql-admins'
  objectId: '00000000-0000-0000-0000-000000000000'
  principalType: 'Group'
}
param sqlSku = { name: 'S1', tier: 'Standard' }
param developerIpAllowlist = {}

param alertEmails = ['ops@example.invalid']
param retentionInDays = 90
param logAnalyticsDailyCapGb = -1
param dailyIngestionAlertThresholdGb = 10
param storageContainers = ['uploads']
param keyVaultPurgeProtection = true
param apiReplicas = { min: 2, max: 6 }
param webReplicas = { min: 2, max: 6 }
param logLevel = 'info'
