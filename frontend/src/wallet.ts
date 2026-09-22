import { api, type WalletAuthResult } from "./api";

type Eip1193Provider = {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
  disconnect?: () => Promise<void>;
};

export type WalletOption = {
  id: string;
  name: string;
  icon?: string;
  kind: "injected" | "walletconnect";
  provider?: Eip1193Provider;
};

type Announcement = { info: { uuid: string; name: string; icon: string; rdns: string }; provider: Eip1193Provider };

export const WALLETCONNECT_PROJECT_ID: string = import.meta.env.VITE_WALLETCONNECT_PROJECT_ID || "";

/**
 * Wallets that follow EIP-6963 announce themselves, so MetaMask, Rabby, Coinbase
 * Wallet and the rest appear without a hard-coded list. A bare `window.ethereum`
 * covers older extensions that do not announce.
 */
export function discoverWallets(onChange: (wallets: WalletOption[]) => void): () => void {
  const found = new Map<string, WalletOption>();
  const emit = () => onChange([...found.values()]);
  const handler = (event: Event) => {
    const detail = (event as CustomEvent<Announcement>).detail;
    if (!detail?.provider) return;
    found.set(detail.info.uuid, {
      id: detail.info.uuid, name: detail.info.name, icon: detail.info.icon, kind: "injected", provider: detail.provider,
    });
    emit();
  };
  window.addEventListener("eip6963:announceProvider", handler);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  const legacy = window.setTimeout(() => {
    const injected = (window as unknown as { ethereum?: Eip1193Provider }).ethereum;
    if (injected && found.size === 0) {
      found.set("injected", { id: "injected", name: "Browser wallet", kind: "injected", provider: injected });
      emit();
    }
  }, 350);
  emit();
  return () => {
    window.clearTimeout(legacy);
    window.removeEventListener("eip6963:announceProvider", handler);
  };
}

const toHex = (text: string) =>
  "0x" + [...new TextEncoder().encode(text)].map((byte) => byte.toString(16).padStart(2, "0")).join("");

async function walletConnectProvider(): Promise<Eip1193Provider> {
  const { EthereumProvider } = await import("@walletconnect/ethereum-provider");
  const provider = await EthereumProvider.init({
    projectId: WALLETCONNECT_PROJECT_ID,
    chains: [1],
    optionalChains: [4663],
    showQrModal: true,
    metadata: { name: "Orbit", description: "Orbit chain intelligence", url: window.location.origin, icons: [`${window.location.origin}/favicon.svg`] },
  });
  await provider.connect();
  return provider as unknown as Eip1193Provider;
}

/** Connect, ask the wallet to sign the server's sign-in message, and let the server verify it. */
export async function signInWithWallet(option: WalletOption): Promise<WalletAuthResult> {
  const provider = option.kind === "walletconnect" ? await walletConnectProvider() : option.provider!;
  const accounts = (await provider.request({ method: "eth_requestAccounts" })) as string[];
  const address = accounts?.[0];
  if (!address) throw new Error("The wallet did not share an account");
  const challenge = await api.walletNonce();
  const message =
    `${challenge.domain} wants you to sign in with your Ethereum account:\n${address}\n\n` +
    "Sign in to Orbit. This does not send a transaction or cost gas.\n\n" +
    `URI: ${challenge.uri}\nVersion: 1\nChain ID: ${challenge.chain_id}\nNonce: ${challenge.nonce}\nIssued At: ${challenge.issued_at}`;
  const signature = (await provider.request({ method: "personal_sign", params: [toHex(message), address] })) as string;
  try {
    return await api.walletVerify(message, signature);
  } finally {
    if (option.kind === "walletconnect") void provider.disconnect?.().catch(() => undefined);
  }
}

export const shortAddress = (address: string) => `${address.slice(0, 6)}…${address.slice(-4)}`;
export const CONNECT_WALLET_EVENT = "orbit:connect-wallet";
export const openWalletDialog = () => window.dispatchEvent(new Event(CONNECT_WALLET_EVENT));
