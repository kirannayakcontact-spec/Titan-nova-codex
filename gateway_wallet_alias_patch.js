"use strict";

// Gateway wallet alias patch
// Fixes false insufficient-wallet rejects when the admin credited a wallet under a
// linked profile id but WhatsApp entry resolution uses another id for the same phone.
// No new API. No UI. It only normalizes Firebase state after Gateway reads it.

const axios = require("axios");

if (!axios.__titanWalletAliasPatch) {
  axios.__titanWalletAliasPatch = true;

  const oldGet = axios.get.bind(axios);
  const oldRequest = axios.request ? axios.request.bind(axios) : null;

  function phoneKey(value) {
    let d = String(value || "").replace(/\D/g, "");
    if (!d) return "";
    if (d.length === 10) d = "91" + d;
    if (d.length > 12 && d.startsWith("91")) d = d.slice(-12);
    return d;
  }

  function walletScore(w) {
    if (!w || typeof w !== "object") return -1;
    const bal = Number(w.balance || 0);
    const credit = Number(w.creditLimit || 0);
    const hold = Number(w.hold || w.walletHold || 0);
    const ledgerCount = Array.isArray(w.ledger) ? w.ledger.length : 0;
    return (bal + credit - hold) + ledgerCount / 100000;
  }

  function clone(obj) {
    try { return JSON.parse(JSON.stringify(obj || {})); } catch (e) { return obj || {}; }
  }

  function mergeWallet(targetId, target, sourceId, source, reason) {
    if (!source || typeof source !== "object") return target;
    if (!target || typeof target !== "object") target = {};
    const out = { ...clone(source), ...clone(target) };

    // Preserve the credited balance/credit from the better source.
    if (walletScore(source) > walletScore(target)) {
      out.balance = Number(source.balance || 0);
      out.creditLimit = Number(source.creditLimit || 0);
      out.hold = Number(source.hold || source.walletHold || 0);
      out.walletHold = out.hold;
      out.ledger = Array.isArray(source.ledger) ? source.ledger.slice() : (Array.isArray(target.ledger) ? target.ledger : []);
    }

    out.userId = targetId;
    out.name = out.name || source.name || targetId;
    out.phone = out.phone || source.phone || "";
    out.walletAliasSyncedFrom = sourceId;
    out.walletAliasSyncedReason = reason || "same_phone";
    out.walletAliasSyncedAt = new Date().toISOString();
    return out;
  }

  function normalizeStateWalletAliases(data) {
    try {
      if (!data || typeof data !== "object") return data;
      const profiles = data.profiles && typeof data.profiles === "object" ? data.profiles : {};
      const wallets = data.wallets && typeof data.wallets === "object" ? data.wallets : {};
      data.wallets = wallets;

      const walletsByPhone = {};
      for (const [wid, w] of Object.entries(wallets)) {
        if (!w || typeof w !== "object") continue;
        const phone = phoneKey(w.phone || wid);
        if (!phone) continue;
        const old = walletsByPhone[phone];
        if (!old || walletScore(w) > walletScore(old.wallet)) walletsByPhone[phone] = { id: wid, wallet: w };
      }

      for (const [pid, prof] of Object.entries(profiles)) {
        if (!prof || typeof prof !== "object" || String(pid).startsWith("admin")) continue;
        const phone = phoneKey(prof.phone || pid);
        if (!phone) continue;

        const canonicalClientId = "client_" + phone;
        const byPhone = walletsByPhone[phone];
        const byClient = wallets[canonicalClientId] && typeof wallets[canonicalClientId] === "object" ? { id: canonicalClientId, wallet: wallets[canonicalClientId] } : null;
        const current = wallets[pid] && typeof wallets[pid] === "object" ? wallets[pid] : null;

        let best = current ? { id: pid, wallet: current } : null;
        for (const cand of [byPhone, byClient]) {
          if (cand && (!best || walletScore(cand.wallet) > walletScore(best.wallet))) best = cand;
        }
        if (best && best.id !== pid) {
          wallets[pid] = mergeWallet(pid, wallets[pid], best.id, best.wallet, "profile_phone_wallet_alias");
        }
      }

      // Reverse alias: if a client_91xxxx profile exists and another wallet with same
      // phone has money, make client_91xxxx see it too.
      for (const [wid, w] of Object.entries({ ...wallets })) {
        const phone = phoneKey((w && w.phone) || wid);
        if (!phone) continue;
        const clientId = "client_" + phone;
        if (profiles[clientId]) {
          const cur = wallets[clientId];
          if (!cur || walletScore(w) > walletScore(cur)) {
            wallets[clientId] = mergeWallet(clientId, cur, wid, w, "client_phone_wallet_alias");
          }
        }
      }
    } catch (e) {
      // Keep Gateway running even if alias normalization fails.
    }
    return data;
  }

  function maybeNormalizeResponse(resp) {
    try {
      if (resp && resp.data && typeof resp.data === "object" && resp.data.profiles) {
        resp.data = normalizeStateWalletAliases(resp.data);
      }
    } catch (e) {}
    return resp;
  }

  axios.get = async function patchedGet() {
    const resp = await oldGet.apply(this, arguments);
    return maybeNormalizeResponse(resp);
  };

  if (oldRequest) {
    axios.request = async function patchedRequest() {
      const resp = await oldRequest.apply(this, arguments);
      return maybeNormalizeResponse(resp);
    };
  }

  console.log("✅ Gateway wallet alias patch active");
}

module.exports = { enabled: true, feature: "gateway_wallet_alias_patch" };
