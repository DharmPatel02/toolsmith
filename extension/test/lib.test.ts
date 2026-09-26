import { test } from "node:test";
import assert from "node:assert/strict";
import { frameDropReason, isAllowedOrigin, urlTemplate, valueShape } from "../src/lib.ts";

test("urlTemplate drops query and templatizes ids", () => {
  assert.equal(urlTemplate("http://localhost:8081/products/42?q=secret#x"), "http://localhost:8081/products/{id}");
  assert.equal(urlTemplate("http://localhost:8081/orders/3f2b1c4d-1111-2222-3333-444455556666/edit"), "http://localhost:8081/orders/{id}/edit");
  assert.equal(urlTemplate("http://localhost:8081/products"), "http://localhost:8081/products");
});

test("only allow-listed origins pass", () => {
  assert.ok(isAllowedOrigin("http://localhost:8081/products"));
  assert.ok(!isAllowedOrigin("http://localhost:8082/"));
  assert.ok(!isAllowedOrigin("https://mail.google.com/"));
  assert.ok(!isAllowedOrigin(undefined));
  assert.ok(!isAllowedOrigin("chrome://extensions"));
});

test("frame budget: rate limit, heartbeat dropped first, hard cap", () => {
  assert.equal(frameDropReason("click", 10_000, 9_500, 0), "rate_limit");
  assert.equal(frameDropReason("click", 10_000, 8_000, 0), null);
  assert.equal(frameDropReason("heartbeat", 10_000, 0, 240), "heartbeat_budget");
  assert.equal(frameDropReason("click", 10_000, 0, 240), null);
  assert.equal(frameDropReason("click", 10_000, 0, 300), "session_cap");
});

test("valueShape never carries content", () => {
  assert.deepEqual(valueShape("hunter2", "text"), { len: 7, type: "text" });
});
