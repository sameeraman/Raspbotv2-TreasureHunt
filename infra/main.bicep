targetScope = 'resourceGroup'

@description('Base name for all resources')
param baseName string = 'ringo'

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Azure AI Search SKU')
@allowed(['basic', 'standard', 'standard2'])
param searchSku string = 'basic'

@description('Azure OpenAI SKU')
@allowed(['S0'])
param openAiSku string = 'S0'

@description('Azure Speech Services SKU')
@allowed(['S0', 'F0'])
param speechSku string = 'S0'

@description('GPT-5.4-mini deployment capacity (1K TPM units)')
param orchestratorCapacity int = 30

@description('GPT-5.4 deployment capacity (1K TPM units)')
param visionCapacity int = 10

@description('o3 deployment capacity (1K TPM units)')
param plannerCapacity int = 10

@description('text-embedding-3-small deployment capacity (1K TPM units)')
param embeddingCapacity int = 30

@description('Azure AI Search index name')
param searchIndexName string = 'ringo-memory'

@description('Object ID of the service principal to grant Cognitive Services OpenAI User role')
param servicePrincipalObjectId string

// ─── Azure OpenAI ────────────────────────────────────────────────────────────

module openai 'modules/openai.bicep' = {
  name: 'openai-deployment'
  params: {
    name: '${baseName}-openai'
    location: location
    sku: openAiSku
    orchestratorCapacity: orchestratorCapacity
    visionCapacity: visionCapacity
    plannerCapacity: plannerCapacity
    embeddingCapacity: embeddingCapacity
    servicePrincipalObjectId: servicePrincipalObjectId
  }
}

// ─── Azure Speech Services ───────────────────────────────────────────────────

module speech 'modules/speech.bicep' = {
  name: 'speech-deployment'
  params: {
    name: '${baseName}-speech'
    location: location
    sku: speechSku
    servicePrincipalObjectId: servicePrincipalObjectId
  }
}

// ─── Azure AI Search ─────────────────────────────────────────────────────────

module search 'modules/search.bicep' = {
  name: 'search-deployment'
  params: {
    name: '${baseName}-search'
    location: location
    sku: searchSku
    indexName: searchIndexName
  }
}

// ─── Outputs ─────────────────────────────────────────────────────────────────

output openAiEndpoint string = openai.outputs.endpoint
output openAiName string = openai.outputs.name
output speechRegion string = speech.outputs.region
output speechName string = speech.outputs.name
output speechResourceId string = speech.outputs.resourceId
output searchEndpoint string = search.outputs.endpoint
output searchName string = search.outputs.name
