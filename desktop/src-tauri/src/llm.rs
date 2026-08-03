use crate::db::DesktopDb;
use crate::settings::{api_client, load_settings, read_secret};
use chrono::Utc;
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnalyzeRequest {
    pub title: String,
    pub transcript: String,
    pub source_url: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProofreadRequest {
    pub transcript: String,
}

fn endpoint(base: &str, path: &str) -> String {
    format!(
        "{}/{}",
        base.trim_end_matches('/'),
        path.trim_start_matches('/')
    )
}

fn json_content(value: &Value) -> Result<String, String> {
    let content = value
        .pointer("/choices/0/message/content")
        .and_then(Value::as_str)
        .ok_or_else(|| "模型没有返回可解析的文本内容".to_string())?;
    let trimmed = content.trim();
    if let Some(rest) = trimmed.strip_prefix("```json") {
        return Ok(rest.trim().trim_end_matches("```").trim().to_string());
    }
    if let Some(rest) = trimmed.strip_prefix("```") {
        return Ok(rest.trim().trim_end_matches("```").trim().to_string());
    }
    Ok(trimmed.to_string())
}

async fn chat_json(db: &DesktopDb, system: &str, user: &str) -> Result<(Value, String), String> {
    let settings = load_settings(db)?;
    if settings.llm_mode == "offline" {
        return Err("模型模式为 offline；请先在系统诊断配置真实模型连接".into());
    }
    if settings.llm_model.trim().is_empty() {
        return Err("尚未配置模型名称".into());
    }
    let key = read_secret("llm_api_key")?
        .ok_or_else(|| "尚未在系统凭据库保存模型 API Key".to_string())?;
    let body = json!({
        "model": settings.llm_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
    });
    let (http, _) = api_client(&settings, 120)?;
    let url = endpoint(&settings.llm_api_base, "chat/completions");
    let response = http
        .post(&url)
        .bearer_auth(&key)
        .json(&body)
        .send()
        .await
        .map_err(|error| format!("模型连接失败：{error}"))?;
    let mut status = response.status();
    let mut raw = response.text().await.map_err(|error| error.to_string())?;
    if status == reqwest::StatusCode::BAD_REQUEST
        && raw.to_ascii_lowercase().contains("response_format")
    {
        let mut fallback = body.clone();
        fallback
            .as_object_mut()
            .map(|object| object.remove("response_format"));
        let response = http
            .post(&url)
            .bearer_auth(&key)
            .json(&fallback)
            .send()
            .await
            .map_err(|error| format!("模型兼容请求失败：{error}"))?;
        status = response.status();
        raw = response.text().await.map_err(|error| error.to_string())?;
    }
    if !status.is_success() {
        let detail = serde_json::from_str::<Value>(&raw)
            .ok()
            .and_then(|value| {
                value
                    .pointer("/error/message")
                    .and_then(Value::as_str)
                    .map(ToOwned::to_owned)
            })
            .unwrap_or_else(|| raw.chars().take(300).collect());
        return Err(format!("模型请求失败（{status}）：{detail}"));
    }
    let envelope: Value =
        serde_json::from_str(&raw).map_err(|error| format!("模型响应不是 JSON：{error}"))?;
    let parsed = serde_json::from_str(&json_content(&envelope)?)
        .map_err(|error| format!("模型内容不是有效 JSON：{error}"))?;
    Ok((parsed, settings.llm_model))
}

fn required_text(value: &Value, key: &str) -> Result<String, String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .ok_or_else(|| format!("模型结果缺少 {key}"))
}

pub async fn analyze_transcript(db: &DesktopDb, request: AnalyzeRequest) -> Result<Value, String> {
    let transcript = request.transcript.trim();
    if transcript.chars().count() < 40 {
        return Err("真实稿件至少需要 40 个字才能拆解".into());
    }
    let system = r#"你是短视频写作 Skill 资产分析器。真实稿件只是一份观察写法的样本，绝不是 Skill 的适用题材。只分析用户提供的真实稿件，不补造事实，不做视频摘要；直接提炼可在完全不同题材中调用的写作机制。

输出不得保留、复述或扩展样本的行业、地点、机构、人物关系、具体事件、数字、画面意象、价值立场或相邻领域标签。name、purpose、hook、progression、ending、riskBoundary 都必须描述通用的写作功能和叙事关系：name 是中性结构命名；purpose 说明任何已有素材的人可解决的写作困难；hook 写注意力机制；progression 写可替换的叙事模块和顺序；ending 写通用认知收束；riskBoundary 只限制事实、引用、立场和仿写风险。若将结果换到消费、职场、人物、产品、热点、知识等不同素材中不能成立，就继续抽象。

只返回 JSON，字段必须为 name、purpose、hook、progression、ending、riskBoundary。每个字段都使用中文完整句子；name 不要带“候选”字样。"#;
    let user = format!(
        "标题：{}\n来源：{}\n\n真实稿件：\n{}",
        request.title.trim(),
        request.source_url.as_deref().unwrap_or("本机已授权来源"),
        transcript
    );
    let (value, _) = chat_json(db, system, &user).await?;
    Ok(json!({
        "name": required_text(&value, "name")?,
        "purpose": required_text(&value, "purpose")?,
        "hook": required_text(&value, "hook")?,
        "progression": required_text(&value, "progression")?,
        "ending": required_text(&value, "ending")?,
        "riskBoundary": required_text(&value, "riskBoundary")?,
        "sourceCount": 1
    }))
}

pub async fn proofread_transcript(db: &DesktopDb, request: ProofreadRequest) -> Result<Value, String> {
    let transcript = request.transcript.trim();
    if transcript.chars().count() < 40 {
        return Err("真实稿件至少需要 40 个字才能校对".into());
    }
    let system = r#"你是中文短视频口播稿校对编辑。只依据给出的 ASR 真实转写稿，识别错别字、同音误识别、明显漏字、重复字和会改变上下文语义的错误。绝不补造未出现的事实、人名、数字或情节；无法确认的内容必须放入 uncertainties，不得擅自改写。先按语义组织自然段，再返回 JSON：formattedTranscript（保留全部原意、以空行分隔自然段的完整稿件）、corrections（数组，每项含 original、replacement、reason、confidence；confidence 为 0-100 整数）、uncertainties（字符串数组）。没有可确认修改时 corrections 返回空数组。"#;
    let user = format!("请校对并分段以下真实转写稿：\n\n{}", transcript);
    let (value, model) = chat_json(db, system, &user).await?;
    let formatted = required_text(&value, "formattedTranscript")?;
    let corrections = value
        .get("corrections")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .enumerate()
                .filter_map(|(index, item)| {
                    let original = item.get("original").and_then(Value::as_str)?.trim();
                    let replacement = item.get("replacement").and_then(Value::as_str)?.trim();
                    let reason = item.get("reason").and_then(Value::as_str)?.trim();
                    if original.is_empty() || replacement.is_empty() || original == replacement || reason.is_empty() {
                        return None;
                    }
                    let confidence = item.get("confidence").and_then(Value::as_f64).unwrap_or(0.0).clamp(0.0, 100.0).round() as u8;
                    Some(json!({
                        "id": format!("correction-{}", index + 1),
                        "original": original,
                        "replacement": replacement,
                        "reason": reason,
                        "confidence": confidence,
                        "status": "pending"
                    }))
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let uncertainties = value
        .get("uncertainties")
        .and_then(Value::as_array)
        .map(|items| items.iter().filter_map(Value::as_str).map(str::trim).filter(|item| !item.is_empty()).collect::<Vec<_>>())
        .unwrap_or_default();
    Ok(json!({
        "originalTranscript": transcript,
        "formattedTranscript": formatted,
        "corrections": corrections,
        "uncertainties": uncertainties,
        "provider": model
    }))
}

pub async fn evaluate_candidate(db: &DesktopDb, candidate: Value) -> Result<Value, String> {
    let source_count = candidate
        .get("sourceCount")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    if source_count < 1 {
        return Err("至少需要 1 条已授权真实稿件后才能运行模型评测".into());
    }
    let candidate_json =
        serde_json::to_string_pretty(&candidate).map_err(|error| error.to_string())?;
    let system = r#"你是写作 Skill 发布评测器。评测对象是从一条已授权真实稿件中提炼出的通用写作机制，不是该稿件所属行业、事件或人物的内容模板。评估候选是否只保留可迁移的写作手法，是否可在完全不同题材中使用，是否避免逐句仿写，风险边界是否清晰。高分候选的 name、purpose、hook、progression、ending 都应描述写作功能和叙事关系，而不是来源的主体类型、行业、场景、对象、立场或价值结论。若仍把来源视频泛化为某个相邻领域（例如从一座城市泛化为城市治理、从一个品牌泛化为机构形象），属于题材过拟合，不能通过。单条真实稿件可以沉淀一个 Skill，但它只能作为手法样本。只返回 JSON：score（0-100 整数）、passed（布尔值）、summary（中文结论）、strengths（字符串数组）、risks（字符串数组）。score >= 80 才允许 passed=true。不要因为字段齐全自动给高分。"#;
    let (value, model) = chat_json(db, system, &candidate_json).await?;
    let score = value
        .get("score")
        .and_then(Value::as_i64)
        .unwrap_or(0)
        .clamp(0, 100);
    let requested_passed = value
        .get("passed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let passed = requested_passed && score >= 80;
    let summary = required_text(&value, "summary")?;
    Ok(json!({
        "status": if passed { "passed" } else { "failed" },
        "score": score,
        "evaluator": model,
        "summary": summary,
        "strengths": value.get("strengths").cloned().unwrap_or_else(|| json!([])),
        "risks": value.get("risks").cloned().unwrap_or_else(|| json!([])),
        "evaluatedAt": Utc::now().to_rfc3339()
    }))
}

pub async fn remediate_candidate(db: &DesktopDb, candidate: Value) -> Result<Value, String> {
    let evaluation = candidate
        .get("modelEvaluation")
        .ok_or_else(|| "请先运行一次模型评测，再生成修复草稿".to_string())?;
    if evaluation.get("status").and_then(Value::as_str) != Some("failed") {
        return Err("仅模型评测未通过的候选需要生成修复草稿".into());
    }
    let structure = json!({
        "name": candidate.get("name").and_then(Value::as_str).unwrap_or_default(),
        "purpose": candidate.get("purpose").and_then(Value::as_str).unwrap_or_default(),
        "hook": candidate.get("hook").and_then(Value::as_str).unwrap_or_default(),
        "progression": candidate.get("progression").and_then(Value::as_str).unwrap_or_default(),
        "ending": candidate.get("ending").and_then(Value::as_str).unwrap_or_default(),
        "riskBoundary": candidate.get("riskBoundary").and_then(Value::as_str).unwrap_or_default(),
        "evaluation": {
            "score": evaluation.get("score").and_then(Value::as_i64).unwrap_or(0),
            "summary": evaluation.get("summary").and_then(Value::as_str).unwrap_or_default(),
            "risks": evaluation.get("risks").cloned().unwrap_or_else(|| json!([])),
            "strengths": evaluation.get("strengths").cloned().unwrap_or_else(|| json!([])),
        }
    });
    let system = r#"你是短视频写作 Skill 的抽象编辑。当前候选来自一个视频，但那个视频只是观察写法的样本，绝不是这个 Skill 的适用题材。你的任务是提炼可迁移的写作机制，使完全无关的人、行业、事件、场景也能直接调用这个 Skill。

必须保留原有的写作机制、叙事推进顺序、解决的问题和事实风险边界，例如“预期反差如何建立注意力、信息如何递进、如何从单例收束为普遍判断”。但不得保留或扩大来源视频的主题范围。禁止在结果中出现或暗示来源的主体类型、行业、地点、机构、人物关系、具体事件、数字、画面意象、价值立场；也禁止把具体视频仅泛化为相邻领域模板，例如“公共服务”“城市治理”“机构形象”“品牌传播”“交通服务”。

字段要求：name 使用中性的结构命名；purpose 说明任何已有素材的人在什么写作困难下可调用；hook 只写开头的注意力机制；progression 写成可替换的叙事模块和先后关系；ending 写通用的价值或认知收束机制；riskBoundary 只限制事实、引用、立场和仿写风险。preservedIntent 只能描述写作机制，不能描述样本主题。changes 第一条必须说明已从样本主题抽象为跨题材写法，并逐条说明如何移除了主题残留。

在输出前自检：若将任意字段替换进消费、职场、人物、产品、热点、知识等完全不同素材时不成立，或仍能看出样本所属领域，就继续改写。hook、progression、ending 不得复用原句或连续八个以上原词。不要补造事实，也不要宣称已经通过评测。只返回 JSON，字段必须为 name、purpose、hook、progression、ending、riskBoundary、preservedIntent、changes。changes 是中文字符串数组。"#;
    let (value, model) = chat_json(
        db,
        system,
        &format!("请在不改变结构本意的前提下修复以下候选：\n{}", serde_json::to_string_pretty(&structure).map_err(|error| error.to_string())?),
    )
    .await?;
    let changes = value
        .get("changes")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .take(8)
                .map(ToOwned::to_owned)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if changes.is_empty() {
        return Err("模型结果缺少 changes，无法说明修复范围".into());
    }
    Ok(json!({
        "draft": {
            "name": required_text(&value, "name")?,
            "purpose": required_text(&value, "purpose")?,
            "hook": required_text(&value, "hook")?,
            "progression": required_text(&value, "progression")?,
            "ending": required_text(&value, "ending")?,
            "riskBoundary": required_text(&value, "riskBoundary")?,
            "sourceCount": 1
        },
        "preservedIntent": required_text(&value, "preservedIntent")?,
        "changes": changes,
        "provider": model
    }))
}

pub async fn list_models(db: &DesktopDb) -> Result<Value, String> {
    let key = read_secret("llm_api_key")?.ok_or_else(|| "尚未保存模型 API Key".to_string())?;
    let settings = load_settings(db)?;
    let (http, _) = api_client(&settings, 120)?;
    let response = http
        .get(endpoint(&settings.llm_api_base, "models"))
        .bearer_auth(key)
        .send()
        .await
        .map_err(|error| format!("拉取模型失败：{error}"))?;
    let status = response.status();
    let value: Value = response.json().await.map_err(|error| error.to_string())?;
    if !status.is_success() {
        return Err(value
            .pointer("/error/message")
            .and_then(Value::as_str)
            .unwrap_or("模型服务拒绝请求")
            .to_string());
    }
    let mut models: Vec<String> = value
        .get("data")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|item| {
            item.get("id")
                .and_then(Value::as_str)
                .map(ToOwned::to_owned)
        })
        .collect();
    models.sort();
    models.truncate(200);
    let recommended = if models.contains(&settings.llm_model) {
        settings.llm_model
    } else {
        models
            .iter()
            .find(|model| model.contains("gpt-4.1-mini"))
            .cloned()
            .or_else(|| models.first().cloned())
            .unwrap_or_default()
    };
    Ok(
        json!({"models": models, "recommendedModel": recommended, "message": "已从服务商读取真实模型列表"}),
    )
}

pub async fn test_connection(db: &DesktopDb) -> Result<Value, String> {
    let (value, model) = chat_json(
        db,
        "只返回 JSON：{\"ok\":true,\"message\":\"连接正常\"}",
        "测试模型连接，不要输出其他内容。",
    )
    .await?;
    let passed = value.get("ok").and_then(Value::as_bool).unwrap_or(false);
    Ok(json!({
        "passed": passed,
        "model": model,
        "message": if passed { "模型连接与 JSON 输出均正常" } else { "模型已响应，但未通过结构化输出检查" }
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_fenced_json_content() {
        let value = json!({"choices":[{"message":{"content":"```json\n{\"ok\":true}\n```"}}]});
        assert_eq!(json_content(&value).unwrap(), "{\"ok\":true}");
    }
}
