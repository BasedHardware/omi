/*
  Warnings:

  - You are about to drop the column `timeout` on the `TrackingSession` table. All the data in the column will be lost.
  - Added the required column `expiresAt` to the `TrackingSession` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "TrackingSession" DROP COLUMN "timeout",
ADD COLUMN     "expiresAt" TIMESTAMP(3) NOT NULL;
