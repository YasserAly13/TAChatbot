// ─────────────────────────────────────────────────────────────────────────────
// ⚠ ASSUMED INTERFACE — PLACEHOLDER UNTIL THE INFRA TEAM'S FILE ARRIVES (D9)
//
// Replace wholesale with the infra team's `sql-database.bicep`; then adjust the module
// call in main.bicep. Never edit a vendored block in a project.
// ─────────────────────────────────────────────────────────────────────────────
//
// Azure SQL (decision D6): one logical server + one database per use case, Entra-only
// authentication (no SQL passwords exist), TLS 1.2, public endpoint with firewall rules
// (Azure services + developer IPs) for now. The api connects with its managed identity
// (`Authentication=ActiveDirectoryMsi`, ADR-0008). Creating the identity's CONTAINED USER
// in the database is a human step after the first deploy (infra/README.md).

@description('Logical server name, globally unique, lowercase (sql-<slug>-<env>).')
param serverName string

@description('Database name.')
param databaseName string

@description('Region.')
param location string

@description('Tags.')
param tags object = {}

@description('Entra admin of the server — a GROUP is recommended. { login, objectId, principalType: "Group" | "User" | "Application" }')
param entraAdmin object

@description('Database SKU, e.g. { name: "GP_S_Gen5", tier: "GeneralPurpose", family: "Gen5", capacity: 1 } (serverless) or { name: "S0", tier: "Standard" }.')
param sku object = {
  name: 'GP_S_Gen5'
  tier: 'GeneralPurpose'
  family: 'Gen5'
  capacity: 1
}

@description('Serverless auto-pause delay in minutes (-1 = never). Ignored for provisioned SKUs.')
param autoPauseDelayMinutes int = 60

@description('Max size in bytes (default 32 GB).')
param maxSizeBytes int = 34359738368

@description('Developer IPs allowed through the firewall: { alice: "203.0.113.10", … }. Keep empty in prod.')
param developerIpAllowlist object = {}

@description('Zone redundancy (prod).')
param zoneRedundant bool = false

resource server 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  tags: tags
  properties: {
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true
      login: entraAdmin.login
      sid: entraAdmin.objectId
      tenantId: tenant().tenantId
      principalType: entraAdmin.principalType
    }
  }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: server
  name: databaseName
  location: location
  tags: tags
  sku: sku
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: maxSizeBytes
    zoneRedundant: zoneRedundant
    autoPauseDelay: startsWith(sku.name, 'GP_S_') ? autoPauseDelayMinutes : null
    requestedBackupStorageRedundancy: zoneRedundant ? 'Zone' : 'Local'
  }
}

// Azure services (Container Apps, the migration runner) — the special 0.0.0.0 rule.
resource allowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: server
  name: 'AllowAllWindowsAzureIps'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource developerRules 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = [
  for item in items(developerIpAllowlist): {
    parent: server
    name: 'dev-${item.key}'
    properties: { startIpAddress: item.value, endIpAddress: item.value }
  }
]

output serverId string = server.id
output serverName string = server.name
output serverFqdn string = server.properties.fullyQualifiedDomainName
output databaseId string = database.id
output databaseName string = database.name
