@description('Azure OpenAI resource name')
param name string

@description('Azure region')
param location string

@description('SKU name')
param sku string

@description('GPT-5.4-mini capacity (1K TPM units)')
param orchestratorCapacity int

@description('GPT-5.4 capacity (1K TPM units)')
param visionCapacity int

@description('o3 capacity (1K TPM units)')
param plannerCapacity int

@description('text-embedding-3-small capacity (1K TPM units)')
param embeddingCapacity int

@description('Object ID of the service principal for role assignment')
param servicePrincipalObjectId string

// Cognitive Services OpenAI User role definition ID
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource openai 'Microsoft.CognitiveServices/accounts@2026-05-01' = {
  name: name
  location: location
  kind: 'OpenAI'
  sku: {
    name: sku
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
  }
}

resource orchestratorDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-01' = {
  parent: openai
  name: 'gpt-5.4-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: orchestratorCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-mini'
      version: '2026-03-17'
    }
  }
}

resource visionDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-01' = {
  parent: openai
  name: 'gpt-5.4'
  sku: {
    name: 'GlobalStandard'
    capacity: visionCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4'
      version: '2026-03-05'
    }
  }
  dependsOn: [orchestratorDeployment]
}

resource plannerDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-01' = {
  parent: openai
  name: 'o3'
  sku: {
    name: 'GlobalStandard'
    capacity: plannerCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'o3'
      version: '2025-04-16'
    }
  }
  dependsOn: [visionDeployment]
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-01' = {
  parent: openai
  name: 'text-embedding-3-small'
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
  }
  dependsOn: [plannerDeployment]
}

// Grant the service principal "Cognitive Services OpenAI User" role on the OpenAI resource
resource openaiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, servicePrincipalObjectId, cognitiveServicesOpenAIUserRoleId)
  scope: openai
  properties: {
    principalId: servicePrincipalObjectId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

output endpoint string = openai.properties.endpoint
output name string = openai.name
