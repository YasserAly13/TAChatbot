// ─────────────────────────────────────────────────────────────────────────────
// ⚠ ASSUMED INTERFACE — PLACEHOLDER UNTIL THE INFRA TEAM'S FILE ARRIVES (D9)
//
// The infra team provides the Bicep building blocks; this file stands in with the
// interface main.bicep expects, so the template compiles and deploys today. When the
// real `key-vault.bicep` is delivered: replace this file wholesale, then adjust the
// module call in main.bicep to its parameters. Never edit a vendored block in a project.
// ─────────────────────────────────────────────────────────────────────────────
//
// Key Vault for one use case: holds the strings its apps read (App Insights connection
// string, DATABASE-URL, …). Access via ACCESS POLICIES, not RBAC, on purpose: granting an
// RBAC role needs Microsoft.Authorization/roleAssignments/write, which the environment's
// deployment identity (Contributor) does not have. Container Apps read secrets through
// their user-assigned identity (secret get/list).

@description('Vault name, 3–24 chars, globally unique (kv-<slug>-<env>).')
@minLength(3)
@maxLength(24)
param name string

@description('Region.')
param location string

@description('Tags.')
param tags object = {}

@description('Principal IDs that may GET/LIST secrets (the apps\' identities).')
param secretReaderPrincipalIds array = []

@description('Principal IDs that may also SET/DELETE secrets (operators, the deployment SP).')
param secretOfficerPrincipalIds array = []

@description('Names of the secrets to create — kept separate from the values so the loop is not over a secure value.')
param secretNames array = []

@description('Secret values keyed by name. Must contain every name in secretNames.')
@secure()
param secrets object = {}

@description('Keep deleted vaults/secrets recoverable; cannot be turned off once on. True in prod.')
param purgeProtectionEnabled bool = false

@description('Soft-delete retention in days (7–90).')
@minValue(7)
@maxValue(90)
param softDeleteRetentionInDays int = 7

var readerPolicies = [
  for principalId in secretReaderPrincipalIds: {
    tenantId: tenant().tenantId
    objectId: principalId
    permissions: { secrets: ['get', 'list'] }
  }
]

var officerPolicies = [
  for principalId in secretOfficerPrincipalIds: {
    tenantId: tenant().tenantId
    objectId: principalId
    permissions: { secrets: ['get', 'list', 'set', 'delete', 'recover', 'backup', 'restore'] }
  }
]

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: false
    enableSoftDelete: true
    softDeleteRetentionInDays: softDeleteRetentionInDays
    enablePurgeProtection: purgeProtectionEnabled ? true : null
    publicNetworkAccess: 'Enabled'
    networkAcls: { defaultAction: 'Allow', bypass: 'AzureServices' }
    accessPolicies: concat(readerPolicies, officerPolicies)
  }
}

resource secretResources 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = [
  for secretName in secretNames: {
    parent: vault
    name: secretName
    properties: {
      value: secrets[secretName]
      contentType: 'text/plain'
    }
  }
]

output id string = vault.id
output name string = vault.name
output uri string = vault.properties.vaultUri
