declare module "virtual:douyin-skill-repository" {
  interface RepositorySkill {
    id: string
    name: string
    account_type: string
    quality_score: number
    source_count: number
    created_at: string
    hotspot_types: string[]
    solves_problems: string[]
    applicable_scenes: string[]
    choose_when: string
    writing_method: string
    risk_boundary: string
    reference_file: string
  }

  const data: {
    version: string
    updatedAt: string
    packagePath: string
    name: string
    skills: RepositorySkill[]
    runtimeFiles: Record<string, string>
  }
  export default data
}
