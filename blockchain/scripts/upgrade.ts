/**
 * Upgrade the DepositToken implementation behind an existing UUPS proxy.
 *
 * Usage:
 *   npx hardhat run scripts/upgrade.ts --network sepolia
 *   npx hardhat run scripts/upgrade.ts --network localhost
 *
 * Reads the proxy address from deployment-{ASSET_TYPE}-{NETWORK_LABEL}.json.
 * The proxy address (and therefore all stored balances) never changes.
 */
import { ethers, network, upgrades } from "hardhat";
import * as fs from "fs";
import * as path from "path";
import * as admin from "firebase-admin";

function getFlag(flag: string, fallback: string): string {
  const args = process.argv;
  const idx = args.indexOf(flag);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return fallback;
}

function initFirestore(): admin.firestore.Firestore | null {
  const credPath =
    process.env.GOOGLE_APPLICATION_CREDENTIALS ??
    path.join(__dirname, "../../backend/secrets/firebase-credentials.json");
  if (!fs.existsSync(credPath)) return null;
  if (!admin.apps.length) {
    admin.initializeApp({ credential: admin.credential.cert(credPath) });
  }
  return admin.firestore();
}

async function main(): Promise<void> {
  const [deployer] = await ethers.getSigners();

  const assetType = getFlag("--asset-type", process.env.ASSET_TYPE ?? "USD");
  const defaultLabel = network.name === "localhost" ? "hardhat" : network.name;
  const networkLabel = getFlag("--network-label", process.env.NETWORK_LABEL ?? defaultLabel);

  const deploymentFile = path.join(__dirname, `../deployment-${assetType}-${networkLabel}.json`);
  if (!fs.existsSync(deploymentFile)) {
    throw new Error(`Deployment file not found: ${deploymentFile}. Deploy first.`);
  }

  const deployment = JSON.parse(fs.readFileSync(deploymentFile, "utf8"));
  const proxyAddress: string = deployment.proxyAddress ?? deployment.contractAddress;

  console.log("Upgrading proxy at:    ", proxyAddress);
  console.log("Upgrading with account:", deployer.address);

  const NewFactory = await ethers.getContractFactory("DepositToken");
  const upgraded = await upgrades.upgradeProxy(proxyAddress, NewFactory, { kind: "uups" });
  await upgraded.waitForDeployment();

  const newImpl = await upgrades.erc1967.getImplementationAddress(proxyAddress);
  const upgradedAt = new Date().toISOString();

  console.log("New implementation:    ", newImpl);
  console.log("Proxy address unchanged:", proxyAddress);

  // Update deployment JSON with new implementation address
  const artifactPath = path.join(
    __dirname,
    "../artifacts/contracts/DepositToken.sol/DepositToken.json"
  );
  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));

  const updated = {
    ...deployment,
    implementationAddress: newImpl,
    upgradedAt,
    abi: artifact.abi,
  };
  fs.writeFileSync(deploymentFile, JSON.stringify(updated, null, 2));
  console.log("Deployment info updated:", deploymentFile);

  // Update Firestore with new implementation address
  const db = initFirestore();
  if (db) {
    const docId = `${assetType}_${networkLabel}`;
    await db.collection("token_registry").doc(docId).set({
      implementation_address: newImpl,
      upgraded_at: upgradedAt,
    }, { merge: true });
    console.log(`Firestore token_registry/${docId} updated`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error: Error) => {
    console.error(error);
    process.exit(1);
  });
