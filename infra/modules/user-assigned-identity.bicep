// User-assigned managed identity — one per container app (ADR-0012).
// Template-owned (not a cloud-team block): it has no policy content.
//
// Its principalId is what the cloud team needs to grant roles on the SHARED tier
// (AcrPull, Cognitive Services OpenAI User, Search roles) — see infra/grant-request.md.

@description('Identity name, e.g. id-<slug>-<env>-api.')
param name string

@description('Region.')
param location string

@description('Tags applied to the identity.')
param tags object = {}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
  tags: tags
}

output id string = identity.id
output name string = identity.name
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
