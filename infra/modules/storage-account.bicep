// ─────────────────────────────────────────────────────────────────────────────
// ⚠ ASSUMED INTERFACE — PLACEHOLDER UNTIL THE INFRA TEAM'S FILE ARRIVES (D9)
//
// Replace wholesale with the infra team's `storage-account.bicep`; then adjust the module
// call in main.bicep. Never edit a vendored block in a project.
// ─────────────────────────────────────────────────────────────────────────────
//
// General-purpose v2 storage for one use case (uploads, ingestion corpora, exports).
// Hardened defaults: HTTPS only, TLS 1.2, no public blob access, shared-key access off
// (apps use their managed identity — "Storage Blob Data Contributor" is a grant on OUR
// resource and is listed in grant-request.md because Contributor cannot assign roles).

@description('Account name: 3–24 lowercase alphanumerics, globally unique (st<slug><env>).')
@minLength(3)
@maxLength(24)
param name string

@description('Region.')
param location string

@description('Tags.')
param tags object = {}

@description('Replication SKU.')
@allowed(['Standard_LRS', 'Standard_ZRS', 'Standard_GRS', 'Standard_RAGRS'])
param skuName string = 'Standard_LRS'

@description('Blob containers to create.')
param containers array = []

@description('Allow Shared Key (account key) access. Keep false; identities only.')
param allowSharedKeyAccess bool = false

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: skuName }
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: allowSharedKeyAccess
    publicNetworkAccess: 'Enabled'
    networkAcls: { defaultAction: 'Allow', bypass: 'AzureServices' }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource blobContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for containerName in containers: {
    parent: blobService
    name: containerName
    properties: { publicAccess: 'None' }
  }
]

output id string = account.id
output name string = account.name
output blobEndpoint string = account.properties.primaryEndpoints.blob
