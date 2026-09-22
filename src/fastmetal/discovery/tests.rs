use super::*;

#[test]
fn observed_model_catalog_and_details_are_projected_without_unknown_fields() {
    let value: Value = serde_json::from_str(include_str!("fixtures/catalog.json")).unwrap();
    let catalog = models(tool_data(value["result"].clone()).unwrap()).unwrap();
    assert_eq!(catalog.len(), 3);
    assert!(
        catalog
            .iter()
            .any(|m| m.id == "gpt-4.1-nano" && m.supports_vision == Some(true))
    );
    let mut quota = json!({"balance":10,"spend":1,"max_budget":11,"key":"PRIVATE","video":{"secret":"PRIVATE"}});
    let q: Quota = serde_json::from_value(quota.take()).unwrap();
    assert!(!serde_json::to_string(&q).unwrap().contains("PRIVATE"));
}
#[test]
fn sse_handles_fragmented_utf8_multiline_comments_and_line_endings() {
    for newline in ["\n", "\r\n", "\r"] {
        let body = [
            ": ping",
            "event: message",
            "data: {\"jsonrpc\":\"2.0\",",
            "data: \"id\":7,\"result\":{\"label\":\"円\"}}",
            "",
            "",
        ]
        .join(newline);
        let mut sse = Sse::default();
        let mut result = None;
        for byte in body.as_bytes() {
            if let Some(value) = sse.feed(&[*byte], 7).unwrap() {
                result = Some(value);
            }
        }
        assert_eq!(result.unwrap()["label"], "円");
    }
}
#[test]
fn notifications_are_ignored_but_wrong_ids_and_server_requests_are_rejected() {
    let mut sse = Sse::default();
    assert!(
        sse.feed(
            b"data: {\"jsonrpc\":\"2.0\",\"method\":\"notifications/progress\"}\n\n",
            1
        )
        .unwrap()
        .is_none()
    );
    for value in [
        json!({"jsonrpc":"2.0","id":2,"result":{}}),
        json!({"jsonrpc":"2.0","id":1,"method":"sampling/createMessage"}),
        json!({"jsonrpc":"2.0","id":1,"error":{"message":"PRIVATE"}}),
        json!({"jsonrpc":"1.0","id":1,"result":{}}),
    ] {
        let error = rpc_result(&serde_json::to_vec(&value).unwrap(), 1).unwrap_err();
        assert!(!error.contains("PRIVATE"));
    }
    let mut sse = Sse::default();
    assert!(
        sse.feed(b"data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n", 1)
            .unwrap()
            .is_none()
    );
}
#[test]
fn incompatible_schemas_and_error_tool_results_are_rejected() {
    assert!(
        validate_schema(
            &json!({"inputSchema":{"type":"object","required":["prompt"]}}),
            false
        )
        .is_err()
    );
    assert!(
        validate_schema(
            &json!({"inputSchema":{"type":"object","properties":{"model":{"type":"number"}}}}),
            true
        )
        .is_err()
    );
    assert!(tool_data(json!({"isError":true,"structuredContent":{}})).is_err());
    assert!(tool_data(json!({"content":[{"type":"text","text":"not JSON"}]})).is_err());
    assert_eq!(
        tool_data(json!({"content":[{"type":"text","text":"{\"count\":3}"}]})).unwrap()["count"],
        3
    );
}
#[test]
fn catalog_counts_duplicates_prices_and_destination_rules_fail_closed() {
    let good =
        json!({"id":"fixed-model","type":"text","supports_vision":true,"input_per_1m_yen":1});
    assert!(models(json!({"count":2,"models":[good.clone()]})).is_err());
    assert!(models(json!({"count":2,"models":[good.clone(),good.clone()]})).is_err());
    let mut bad = good;
    bad["input_per_1m_yen"] = json!(-1);
    assert!(models(json!({"count":1,"models":[bad]})).is_err());
    for url in [
        "http://localhost/mcp",
        "https://127.0.0.1/mcp",
        "http://127.0.0.1/mcp?key=x",
        "http://example.com/mcp",
        "http://user@127.0.0.1/mcp",
    ] {
        assert!(Client::new(None, Some(url)).is_err());
    }
    assert!(Client::new(Some("secret".into()), Some("http://127.0.0.1/mcp")).is_err());
    assert!(Client::new(None, None).is_err());
}
