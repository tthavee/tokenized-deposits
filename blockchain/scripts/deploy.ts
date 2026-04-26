import { ethers, network, upgrades } from "hardhat";
import * as fs from "fs";
import * as path from "path";
import * as admin from "firebase-admin";

// ---------------------------------------------------------------------------
// CLI flag parsing — supports: -- --asset-type USD --network-label localhost
// ---------------------------------------------------------------------------
function getFlag(flag: string, fallback: string): string {
  const args = process.argv;
  const idx = args.indexOf(flag);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return fallback;
}

// ---------------------------------------------------------------------------
// Firestore initialisation (lazy — skipped if credentials are absent)
// ---------------------------------------------------------------------------
function initFirestore(): admin.firestore.Firestore | null {
  const credPath =
    process.env.GOOGLE_APPLICATION_CREDENTIALS ??
    path.join(__dirname, "../../backend/secrets/firebase-credentials.json");

  if (!fs.existsSync(credPath)) {
    console.warn(`[firestore] credentials not found at ${credPath} — skipping Firestore write`);
    return null;
  }

  if (!admin.apps.length) {
    admin.initializeApp({ credential: admin.credential.cert(credPath) });
  }
  return admin.firestore();
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main(): Promise<void> {
  const [deployer] = await ethers.getSigners();

  const assetType = getFlag("--asset-type", process.env.ASSET_TYPE ?? "USD");
  const defaultLabel = network.name === "localhost" ? "hardhat" : network.name;
  const networkLabel = getFlag("--network-label", process.env.NETWORK_LABEL ?? defaultLabel);

  console.log("Deploying contracts with account:", deployer.address);
  console.log(
    "Account balance:",
    (await ethers.provider.getBalance(deployer.address)).toString()
  );
  console.log(`Asset type: ${assetType}  |  Network: ${networkLabel}`);

  // Deploy via UUPS proxy — proxy address is permanent, implementation can be upgraded.
  const Factory = await ethers.getContractFactory("DepositToken");
  const proxy = await upgrades.deployProxy(
    Factory,
    [assetType, networkLabel, deployer.address],
    { kind: "uups" }
  );
  await proxy.waitForDeployment();

  const proxyAddress = await proxy.getAddress();
  const implementationAddress = await upgrades.erc1967.getImplementationAddress(proxyAddress);
  const deployedAt = new Date().toISOString();

  console.log("Proxy (permanent address):", proxyAddress);
  console.log("Implementation:           ", implementationAddress);

  // Load ABI from the implementation artifact
  const artifactPath = path.join(
    __dirname,
    "../artifacts/contracts/DepositToken.sol/DepositToken.json"
  );
  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));

  // Save deployment-{asset_type}-{network}.json
  const deploymentInfo = {
    contractAddress: proxyAddress,        // proxy — use this everywhere
    proxyAddress,
    implementationAddress,
    assetType,
    networkLabel,
    deployer: deployer.address,
    network: network.name,
    chainId: (await ethers.provider.getNetwork()).chainId.toString(),
    deployedAt,
    abi: artifact.abi,
  };

  const outputFileName = `deployment-${assetType}-${networkLabel}.json`;
  const outputPath = path.join(__dirname, "..", outputFileName);
  fs.writeFileSync(outputPath, JSON.stringify(deploymentInfo, null, 2));
  console.log("Deployment info saved to:", outputPath);

  // Write to Firestore token_registry/{asset_type}_{network}
  const db = initFirestore();
  if (db) {
    const docId = `${assetType}_${networkLabel}`;
    await db.collection("token_registry").doc(docId).set({
      contract_address: proxyAddress,
      proxy_address: proxyAddress,
      implementation_address: implementationAddress,
      asset_type: assetType,
      network: networkLabel,
      deployed_at: deployedAt,
      deployer_address: deployer.address,
    });
    console.log(`Firestore token_registry/${docId} updated`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error: Error) => {
    console.error(error);
    process.exit(1);
  });
